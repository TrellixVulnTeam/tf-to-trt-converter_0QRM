# Model download and UFF convertion utils
import os
import sys
import tarfile

import requests
import tensorflow as tf
import tensorrt as trt
import graphsurgeon as gs
import uff

from utils.paths import PATHS


# UFF conversion functionality

# This class contains converted (UFF) model metadata
class ModelData(object):
    # Name of input node
    INPUT_NAME = "Input"
    # CHW format of model input
    INPUT_SHAPE = (3, 300, 300)
    # Name of output node
    OUTPUT_NAME = "NMS"

    @staticmethod
    def get_input_channels():
        return ModelData.INPUT_SHAPE[0]

    @staticmethod
    def get_input_height():
        return ModelData.INPUT_SHAPE[1]

    @staticmethod
    def get_input_width():
        return ModelData.INPUT_SHAPE[2]


def ssd_unsupported_nodes_to_plugin_nodes(ssd_graph):
    """Makes ssd_graph TensorRT comparible using graphsurgeon.

    This function takes ssd_graph, which contains graphsurgeon
    DynamicGraph data structure. This structure describes frozen Tensorflow
    graph, that can be modified using graphsurgeon (by deleting, adding,
    replacing certain nodes). The graph is modified by removing
    Tensorflow operations that are not supported by TensorRT's UffParser
    and replacing them with custom layer plugin nodes.

    Note: This specific implementation works only for
    ssd_inception_v2_coco_2017_11_17 network.

    Args:
        ssd_graph (gs.DynamicGraph): graph to convert
    Returns:
        gs.DynamicGraph: UffParser compatible SSD graph
    """
    # Create TRT plugin nodes to replace unsupported ops in Tensorflow graph
    channels = ModelData.get_input_channels()
    height = ModelData.get_input_height()
    width = ModelData.get_input_width()

    Input = gs.create_plugin_node(name="Input",
        op="Placeholder",
        dtype=tf.float32,
        shape=[1, channels, height, width])
    PriorBox = gs.create_plugin_node(name="GridAnchor", op="GridAnchor_TRT",
        minSize=0.2,
        maxSize=0.95,
        aspectRatios=[1.0, 2.0, 0.5, 3.0, 0.33],
        variance=[0.1,0.1,0.2,0.2],
        featureMapShapes=[19, 10, 5, 3, 2, 1],
        numLayers=6
    )
    NMS = gs.create_plugin_node(
        name="NMS",
        op="NMS_TRT",
        shareLocation=1,
        varianceEncodedInTarget=0,
        backgroundLabelId=0,
        confidenceThreshold=1e-8,
        nmsThreshold=0.6,
        topK=100,
        keepTopK=100,
        numClasses=91,
        inputOrder=[0, 2, 1],
        confSigmoid=1,
        isNormalized=1
    )
    concat_priorbox = gs.create_node(
        "concat_priorbox",
        op="ConcatV2",
        dtype=tf.float32,
        axis=2
    )
    concat_box_loc = gs.create_plugin_node(
        "concat_box_loc",
        op="FlattenConcat_TRT",
        dtype=tf.float32,
    )
    concat_box_conf = gs.create_plugin_node(
        "concat_box_conf",
        op="FlattenConcat_TRT",
        dtype=tf.float32,
    )

    # Create a mapping of namespace names -> plugin nodes.
    namespace_plugin_map = {
        "MultipleGridAnchorGenerator": PriorBox,
        "Postprocessor": NMS,
        "Preprocessor": Input,
        "ToFloat": Input,
        "image_tensor": Input,
        "MultipleGridAnchorGenerator/Concatenate": concat_priorbox,
        "MultipleGridAnchorGenerator/Identity": concat_priorbox,
        "concat": concat_box_loc,
        "concat_1": concat_box_conf
    }

    # Create a new graph by collapsing namespaces
    ssd_graph.collapse_namespaces(namespace_plugin_map)
    # Remove the outputs, so we just have a single output node (NMS).
    # If remove_exclusive_dependencies is True, the whole graph will be removed!
    ssd_graph.remove(ssd_graph.graph_outputs, remove_exclusive_dependencies=False)
    return ssd_graph


def ssd_mobilenet_v2_unsupported_nodes_to_plugin_nodes(ssd_graph, input_shape):
    """Makes ssd_graph TensorRT comparible using graphsurgeon.

    This function takes ssd_graph, which contains graphsurgeon
    DynamicGraph data structure. This structure describes frozen Tensorflow
    graph, that can be modified using graphsurgeon (by deleting, adding,
    replacing certain nodes). The graph is modified by removing
    Tensorflow operations that are not supported by TensorRT's UffParser
    and replacing them with custom layer plugin nodes.

    Note: This specific implementation works only for
    ssd_mobilenet_v2_coco_2018_03_29 network.

    Args:
        ssd_graph (gs.DynamicGraph): graph to convert
        input_shape: input shape in CHW format
    Returns:
        gs.DynamicGraph: UffParser compatible SSD graph
    """
    # Create TRT plugin nodes to replace unsupported ops in Tensorflow graph
    # channels = ModelData.get_input_channels()
    # height = ModelData.get_input_height()
    # width = ModelData.get_input_width()

    channels, height, width = input_shape

    Input = gs.create_plugin_node(name="Input",
        op="Placeholder",
        dtype=tf.float32,
        shape=[1, channels, height, width])
    PriorBox = gs.create_plugin_node(name="GridAnchor", op="GridAnchor_TRT",
        minSize=0.2,
        maxSize=0.95,
        aspectRatios=[1.0, 2.0, 0.5, 3.0, 0.33],
        variance=[0.1,0.1,0.2,0.2],
        featureMapShapes=[19, 10, 5, 3, 2, 1],
        numLayers=6
    )
    NMS = gs.create_plugin_node(
        name="NMS",
        op="NMS_TRT",
        shareLocation=1,
        varianceEncodedInTarget=0,
        backgroundLabelId=0,
        confidenceThreshold=1e-8,
        nmsThreshold=0.6,
        topK=100,
        keepTopK=100,
        numClasses=91,
        inputOrder=[1, 0, 2],
        confSigmoid=1,
        isNormalized=1
    )
    concat_priorbox = gs.create_node(
        "concat_priorbox",
        op="ConcatV2",
        dtype=tf.float32,
        axis=2
    )
    concat_box_loc = gs.create_plugin_node(
        "concat_box_loc",
        op="FlattenConcat_TRT",
        dtype=tf.float32,
        axis=1,
        ignoreBatch=0
    )
    concat_box_conf = gs.create_plugin_node(
        "concat_box_conf",
        op="FlattenConcat_TRT",
        dtype=tf.float32,
        axis=1,
        ignoreBatch=0
    )

    # Create a mapping of namespace names -> plugin nodes.
    namespace_plugin_map = {
        "MultipleGridAnchorGenerator": PriorBox,
        "Postprocessor": NMS,
        "Preprocessor/map": Input,
        "ToFloat": Input,
        # "image_tensor": Input,
        "Concatenate": concat_priorbox,
        "concat": concat_box_loc,
        "concat_1": concat_box_conf
    }
    for node in ssd_graph.graph_inputs:
        namespace_plugin_map[node.name] = Input

    # Create a new graph by collapsing namespaces
    ssd_graph.collapse_namespaces(namespace_plugin_map)
    # Remove the outputs, so we just have a single output node (NMS).
    # If remove_exclusive_dependencies is True, the whole graph will be removed!
    ssd_graph.remove(ssd_graph.graph_outputs, remove_exclusive_dependencies=False)
    # Disconnect the Input node from NMS, as it expects to have only 3 inputs.

    to_remove_nodes = ["Input", "Preprocessor/stack_1"]
    for node in to_remove_nodes:
        if node in ssd_graph.find_nodes_by_op("NMS_TRT")[0].input:
            ssd_graph.find_nodes_by_op("NMS_TRT")[0].input.remove(node)

            # For split model part 2
            if node == "Preprocessor/stack_1":
                ssd_graph.remove(node)

    return ssd_graph


def ssd_mobilenet_v1_unsupported_nodes_to_plugin_nodes(ssd_graph, input_shape):
    """Makes ssd_graph TensorRT comparible using graphsurgeon.

    This function takes ssd_graph, which contains graphsurgeon
    DynamicGraph data structure. This structure describes frozen Tensorflow
    graph, that can be modified using graphsurgeon (by deleting, adding,
    replacing certain nodes). The graph is modified by removing
    Tensorflow operations that are not supported by TensorRT's UffParser
    and replacing them with custom layer plugin nodes.

    Note: This specific implementation works only for
    ssd_mobilenet_v2_coco_2018_03_29 network.

    Args:
        ssd_graph (gs.DynamicGraph): graph to convert
        input_shape: input shape in CHW format
    Returns:
        gs.DynamicGraph: UffParser compatible SSD graph
    """
    # Create TRT plugin nodes to replace unsupported ops in Tensorflow graph
    # channels = ModelData.get_input_channels()
    # height = ModelData.get_input_height()
    # width = ModelData.get_input_width()

    channels, height, width = input_shape

    Input = gs.create_plugin_node(name="Input",
                                  op="Placeholder",
                                  dtype=tf.float32,
                                  shape=[1, channels, height, width])
    PriorBox = gs.create_plugin_node(name="GridAnchor", op="GridAnchor_TRT",
                                     minSize=0.2,
                                     maxSize=0.95,
                                     aspectRatios=[1.0, 2.0, 0.5, 3.0, 0.33],
                                     variance=[0.1, 0.1, 0.2, 0.2],
                                     featureMapShapes=[19, 10, 5, 3, 2, 1],
                                     numLayers=6
                                     )
    NMS = gs.create_plugin_node(
        name="NMS",
        op="NMS_TRT",
        shareLocation=1,
        varianceEncodedInTarget=0,
        backgroundLabelId=0,
        confidenceThreshold=1e-8,
        nmsThreshold=0.6,
        topK=100,
        keepTopK=100,
        numClasses=91,
        inputOrder=[1, 0, 2],
        confSigmoid=1,
        isNormalized=1
    )
    concat_priorbox = gs.create_node(
        "concat_priorbox",
        op="ConcatV2",
        dtype=tf.float32,
        axis=2
    )
    concat_box_loc = gs.create_plugin_node(
        "concat_box_loc",
        op="FlattenConcat_TRT",
        dtype=tf.float32,
        axis=1,
        ignoreBatch=0
    )
    concat_box_conf = gs.create_plugin_node(
        "concat_box_conf",
        op="FlattenConcat_TRT",
        dtype=tf.float32,
        axis=1,
        ignoreBatch=0
    )

    # Create a mapping of namespace names -> plugin nodes.
    namespace_plugin_map = {
        "MultipleGridAnchorGenerator": concat_priorbox,
        "Postprocessor": NMS,
        "Preprocessor/map": Input,
        "ToFloat": Input,
        # "image_tensor": Input,
        "strided_slice_6": PriorBox,
        "Concatenate": concat_priorbox,
        "concat": concat_box_loc,
        "concat_1": concat_box_conf
    }
    for node in ssd_graph.graph_inputs:
        namespace_plugin_map[node.name] = Input

    # Create a new graph by collapsing namespaces
    ssd_graph.collapse_namespaces(namespace_plugin_map)
    # Remove the outputs, so we just have a single output node (NMS).
    # If remove_exclusive_dependencies is True, the whole graph will be removed!
    ssd_graph.remove(ssd_graph.graph_outputs, remove_exclusive_dependencies=False)
    # Disconnect the Input node from NMS, as it expects to have only 3 inputs.

    death_list = ["Shape_6", "strided_slice_7"]
    ssd_graph.remove(ssd_graph.find_nodes_by_path(death_list))

    to_remove_nodes = ["Input", "Preprocessor/stack_1"]
    for node in to_remove_nodes:
        if node in ssd_graph.find_nodes_by_op("NMS_TRT")[0].input:
            ssd_graph.find_nodes_by_op("NMS_TRT")[0].input.remove(node)
            if node == "Preprocessor/stack_1":
                ssd_graph.remove(node)

    if "image_tensor:0" in ssd_graph.graph_inputs[0].input:
        ssd_graph.graph_inputs[0].input.remove("image_tensor:0")s

    return ssd_graph


def model_to_uff(model_path, output_uff_path, input_shape,
                 preprocess_func=ssd_unsupported_nodes_to_plugin_nodes, silent=False):
    """Takes frozen .pb graph, converts it to .uff and saves it to file.

    Args:
        model_path (str): .pb model path
        input_shape: input shape in CHW format
        output_uff_path (str): .uff path where the UFF file will be saved
        silent (bool): if True, writes progress messages to stdout

    """
    dynamic_graph = gs.DynamicGraph(model_path)
    dynamic_graph = preprocess_func(dynamic_graph, input_shape=input_shape)

    uff.from_tensorflow(
        dynamic_graph.as_graph_def(),
        [ModelData.OUTPUT_NAME],
        output_filename=output_uff_path,
        text=True
    )


# Model download functionality

def maybe_print(should_print, print_arg):
    """Prints message if supplied boolean flag is true.

    Args:
        should_print (bool): if True, will print print_arg to stdout
        print_arg (str): message to print to stdout
    """
    if should_print:
        print(print_arg)


def maybe_mkdir(dir_path):
    """Makes directory if it doesn't exist.

    Args:
        dir_path (str): directory path
    """
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)


def download_file(file_url, file_dest_path, silent=False):
    """Downloads file from supplied URL and puts it into supplied directory.

    Args:
        file_url (str): URL with file to download
        file_dest_path (str): path to save downloaded file in
        silent (bool): if True, writes progress messages to stdout
    """
    with open(file_dest_path, "wb") as f:
        maybe_print(not silent, "Downloading {}".format(file_dest_path))
        response = requests.get(file_url, stream=True)
        total_length = response.headers.get('content-length')

        if total_length is None or silent: # no content length header or silent, just write file
            f.write(response.content)
        else: # not silent, print progress
            dl = 0
            total_length = int(total_length)
            for data in response.iter_content(chunk_size=4096):
                dl += len(data)
                f.write(data)
                done = int(50 * dl / total_length)
                sys.stdout.write(
                    "\rDownload progress [{}{}] {}%".format(
                        '=' * done, ' ' * (50-done),
                        int(100 * dl / total_length)))
                sys.stdout.flush()
            sys.stdout.write("\n")
            sys.stdout.flush()


def download_model(model_name, silent=False):
    """Downloads model_name from Tensorflow model zoo.

    Args:
        model_name (str): chosen object detection model
        silent (bool): if True, writes progress messages to stdout
    """
    maybe_print(not silent, "Preparing pretrained model")
    model_dir = PATHS.get_models_dir_path()
    maybe_mkdir(model_dir)
    model_url = PATHS.get_model_url(model_name)
    model_archive_path = os.path.join(model_dir, "{}.tar.gz".format(model_name))
    download_file(model_url, model_archive_path, silent)
    maybe_print(not silent, "Download complete\nUnpacking {}".format(model_archive_path))
    with tarfile.open(model_archive_path, "r:gz") as tar:
        tar.extractall(path=model_dir)
    maybe_print(not silent, "Extracting complete\nRemoving {}".format(model_archive_path))
    os.remove(model_archive_path)
    maybe_print(not silent, "Model ready")


def prepare_ssd_model(model_name="ssd_inception_v2_coco_2017_11_17", silent=False):
    """Downloads pretrained object detection model and converts it to UFF.

    The model is downloaded from Tensorflow object detection model zoo.
    Currently only ssd_inception_v2_coco_2017_11_17 model is supported
    due to model_to_uff() using logic specific to that network when converting.

    Args:
        model_name (str): chosen object detection model
        silent (bool): if True, writes progress messages to stdout
    """
    if model_name != "ssd_inception_v2_coco_2017_11_17":
        raise NotImplementedError(
            "Model {} is not supported yet".format(model_name))
    download_model(model_name, silent)
    ssd_pb_path = PATHS.get_model_pb_path(model_name)
    ssd_uff_path = PATHS.get_model_uff_path(model_name)
    model_to_uff(ssd_pb_path, ssd_uff_path, silent=silent)
