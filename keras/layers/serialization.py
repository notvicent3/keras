# Copyright 2015 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Layer serialization/deserialization functions.
"""
# pylint: disable=wildcard-import
# pylint: disable=unused-import

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import tensorflow as tf

import threading
from keras.engine import base_layer
from keras.engine import input_layer
from keras.engine import input_spec
from keras.layers import advanced_activations
from keras.layers import convolutional
from keras.layers import convolutional_recurrent
from keras.layers import core
from keras.layers import cudnn_recurrent
from keras.layers import dense_attention
from keras.layers import einsum_dense
from keras.layers import embeddings
from keras.layers import local
from keras.layers import merge
from keras.layers import multi_head_attention
from keras.layers import noise
from keras.layers import normalization
from keras.layers import normalization_v2
from keras.layers import pooling
from keras.layers import recurrent
from keras.layers import recurrent_v2
from keras.layers import rnn_cell_wrapper_v2
from keras.layers import wrappers
from keras.layers.preprocessing import category_crossing
from keras.layers.preprocessing import category_encoding
from keras.layers.preprocessing import discretization
from keras.layers.preprocessing import hashing
from keras.layers.preprocessing import image_preprocessing
from keras.layers.preprocessing import integer_lookup as preprocessing_integer_lookup
from keras.layers.preprocessing import integer_lookup_v1 as preprocessing_integer_lookup_v1
from keras.layers.preprocessing import normalization as preprocessing_normalization
from keras.layers.preprocessing import normalization_v1 as preprocessing_normalization_v1
from keras.layers.preprocessing import string_lookup as preprocessing_string_lookup
from keras.layers.preprocessing import string_lookup_v1 as preprocessing_string_lookup_v1
from keras.layers.preprocessing import text_vectorization as preprocessing_text_vectorization
from keras.layers.preprocessing import text_vectorization_v1 as preprocessing_text_vectorization_v1
from keras.utils import generic_utils
from keras.utils import tf_inspect as inspect
from tensorflow.python.util.tf_export import keras_export


ALL_MODULES = (base_layer, input_layer, advanced_activations, convolutional,
               convolutional_recurrent, core, cudnn_recurrent, dense_attention,
               embeddings, einsum_dense, local, merge, noise, normalization,
               pooling, image_preprocessing, preprocessing_integer_lookup_v1,
               preprocessing_normalization_v1, preprocessing_string_lookup_v1,
               preprocessing_text_vectorization_v1, recurrent, wrappers,
               hashing, category_crossing, category_encoding, discretization,
               multi_head_attention)
ALL_V2_MODULES = (rnn_cell_wrapper_v2, normalization_v2, recurrent_v2,
                  preprocessing_integer_lookup, preprocessing_normalization,
                  preprocessing_string_lookup, preprocessing_text_vectorization)
# ALL_OBJECTS is meant to be a global mutable. Hence we need to make it
# thread-local to avoid concurrent mutations.
LOCAL = threading.local()


def populate_deserializable_objects():
  """Populates dict ALL_OBJECTS with every built-in layer.
  """
  global LOCAL
  if not hasattr(LOCAL, 'ALL_OBJECTS'):
    LOCAL.ALL_OBJECTS = {}
    LOCAL.GENERATED_WITH_V2 = None

  if LOCAL.ALL_OBJECTS and LOCAL.GENERATED_WITH_V2 == tf.__internal__.tf2.enabled():
    # Objects dict is already generated for the proper TF version:
    # do nothing.
    return

  LOCAL.ALL_OBJECTS = {}
  LOCAL.GENERATED_WITH_V2 = tf.__internal__.tf2.enabled()

  base_cls = base_layer.Layer
  generic_utils.populate_dict_with_module_objects(
      LOCAL.ALL_OBJECTS,
      ALL_MODULES,
      obj_filter=lambda x: inspect.isclass(x) and issubclass(x, base_cls))

  # Overwrite certain V1 objects with V2 versions
  if tf.__internal__.tf2.enabled():
    generic_utils.populate_dict_with_module_objects(
        LOCAL.ALL_OBJECTS,
        ALL_V2_MODULES,
        obj_filter=lambda x: inspect.isclass(x) and issubclass(x, base_cls))

  # These deserialization aliases are added for backward compatibility,
  # as in TF 1.13, "BatchNormalizationV1" and "BatchNormalizationV2"
  # were used as class name for v1 and v2 version of BatchNormalization,
  # respectively. Here we explicitly convert them to their canonical names.
  LOCAL.ALL_OBJECTS['BatchNormalizationV1'] = normalization.BatchNormalization
  LOCAL.ALL_OBJECTS[
      'BatchNormalizationV2'] = normalization_v2.BatchNormalization

  # Prevent circular dependencies.
  from keras import models  # pylint: disable=g-import-not-at-top
  from keras.premade.linear import LinearModel  # pylint: disable=g-import-not-at-top
  from keras.premade.wide_deep import WideDeepModel  # pylint: disable=g-import-not-at-top
  from keras.feature_column.sequence_feature_column import SequenceFeatures  # pylint: disable=g-import-not-at-top

  LOCAL.ALL_OBJECTS['Input'] = input_layer.Input
  LOCAL.ALL_OBJECTS['InputSpec'] = input_spec.InputSpec
  LOCAL.ALL_OBJECTS['Functional'] = models.Functional
  LOCAL.ALL_OBJECTS['Model'] = models.Model
  LOCAL.ALL_OBJECTS['SequenceFeatures'] = SequenceFeatures
  LOCAL.ALL_OBJECTS['Sequential'] = models.Sequential
  LOCAL.ALL_OBJECTS['LinearModel'] = LinearModel
  LOCAL.ALL_OBJECTS['WideDeepModel'] = WideDeepModel

  if tf.__internal__.tf2.enabled():
    from keras.feature_column.dense_features_v2 import DenseFeatures  # pylint: disable=g-import-not-at-top
    LOCAL.ALL_OBJECTS['DenseFeatures'] = DenseFeatures
  else:
    from keras.feature_column.dense_features import DenseFeatures  # pylint: disable=g-import-not-at-top
    LOCAL.ALL_OBJECTS['DenseFeatures'] = DenseFeatures

  # Merge layers, function versions.
  LOCAL.ALL_OBJECTS['add'] = merge.add
  LOCAL.ALL_OBJECTS['subtract'] = merge.subtract
  LOCAL.ALL_OBJECTS['multiply'] = merge.multiply
  LOCAL.ALL_OBJECTS['average'] = merge.average
  LOCAL.ALL_OBJECTS['maximum'] = merge.maximum
  LOCAL.ALL_OBJECTS['minimum'] = merge.minimum
  LOCAL.ALL_OBJECTS['concatenate'] = merge.concatenate
  LOCAL.ALL_OBJECTS['dot'] = merge.dot


@keras_export('keras.layers.serialize')
def serialize(layer):
  return generic_utils.serialize_keras_object(layer)


@keras_export('keras.layers.deserialize')
def deserialize(config, custom_objects=None):
  """Instantiates a layer from a config dictionary.

  Args:
      config: dict of the form {'class_name': str, 'config': dict}
      custom_objects: dict mapping class names (or function names)
          of custom (non-Keras) objects to class/functions

  Returns:
      Layer instance (may be Model, Sequential, Network, Layer...)
  """
  populate_deserializable_objects()
  return generic_utils.deserialize_keras_object(
      config,
      module_objects=LOCAL.ALL_OBJECTS,
      custom_objects=custom_objects,
      printable_module_name='layer')