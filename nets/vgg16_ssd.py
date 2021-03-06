from __future__ import division
import tensorflow as tf
from tensorflow.contrib import layers
from tensorflow.contrib.framework import arg_scope
from nets import ssdnet
import numpy as np


class vgg16_ssd(ssdnet.SSDNet):

    def __init__(self, vgg16_path='ssd/vgg16/vgg16.npy', weight_decay=0.0005,
                 num_classes=20, *args, **kwargs):
        super(vgg16_ssd, self).__init__(name='vgg16_ssd', *args, *kwargs)
        self.vgg16_path = vgg16_path
        self.weight_decay = weight_decay
        self.num_classes = num_classes

    def set_pre_trained_weight_path(self, path):
        self.vgg16_path = path

    def build(self, inputs):
        feature_maps = []
        with arg_scope([layers.conv2d], weights_initializer=layers.xavier_initializer(),
                       weights_regularizer=layers.l2_regularizer(self.weight_decay), padding='SAME'):
            y = inputs
            y = layers.repeat(y, 2, layers.conv2d, 64, [3, 3], 1, scope='conv1')
            y = layers.max_pool2d(y, [2, 2], 2, 'SAME', scope='pool1')
            y = layers.repeat(y, 2, layers.conv2d, 128, [3, 3], 1, scope='conv2')
            y = layers.max_pool2d(y, [2, 2], 2, 'SAME', scope='pool2')
            y = layers.repeat(y, 3, layers.conv2d, 256, [3, 3], 1, scope='conv3')
            y = layers.max_pool2d(y, [2, 2], 2, 'SAME', scope='pool3')
            y = layers.repeat(y, 3, layers.conv2d, 512, [3, 3], 1, scope='conv4')
            with tf.variable_scope('l2_norm'):
                y = self.l2_norm(y, 512)
            feature_maps.append(y)
            y = layers.max_pool2d(y, [2, 2], 2, 'SAME', scope='pool4')
            y = layers.repeat(y, 3, layers.conv2d, 512, [3, 3], 1, scope='conv5')
            y = layers.max_pool2d(y, [3, 3], 1, 'SAME', scope='pool5')
            with tf.variable_scope('fc6'):
                w = tf.get_variable('weights', shape=[3, 3, 512, 1024], dtype=tf.float32)
                b = tf.get_variable('biases', shape=[1024], dtype=tf.float32)
                y = tf.nn.atrous_conv2d(y, w, 6, 'SAME')
                y = tf.nn.bias_add(y, b)
            y = layers.conv2d(y, 1024, [1, 1], 1, scope='fc7')
            feature_maps.append(y)
            y = layers.conv2d(y, 256, [1, 1], 1, scope='conv8_1')
            y = layers.conv2d(y, 512, [3, 3], 2, scope='conv8_2')
            feature_maps.append(y)
            y = layers.conv2d(y, 128, [1, 1], 1, scope='conv9_1')
            y = layers.conv2d(y, 256, [3, 3], 2, scope='conv9_2')
            feature_maps.append(y)
            y = layers.conv2d(y, 128, [1, 1], 1, scope='conv10_1')
            y = layers.conv2d(y, 256, [3, 3], 1, padding='VALID', scope='conv10_2')
            feature_maps.append(y)
            y = layers.conv2d(y, 128, [1, 1], 1, scope='conv11_1')
            y = layers.conv2d(y, 256, [3, 3], 1, padding='VALID',scope='conv11_2')
            feature_maps.append(y)
            self.feature_map_size = [map.get_shape().as_list()[1:3] for map in feature_maps]

            # predictions = []
            self.location = []
            self.classification = []
            for i, feature_map in enumerate(feature_maps):
                num_outputs = self.num_anchors[i] * (self.num_classes + 1 + 4)
                prediction = layers.conv2d(feature_map, num_outputs, [3, 3], 1, scope='pred_%d' % i)

                locations, classifications = tf.split(prediction,
                                                      [self.num_anchors[i] * 4,
                                                       self.num_anchors[i] * (self.num_classes + 1)],
                                                      -1)
                shape = locations.get_shape()
                locations = tf.reshape(locations, [-1,
                                                   shape[1],
                                                   shape[2],
                                                   self.num_anchors[i],
                                                   4])
                shape = classifications.get_shape()
                classifications = tf.reshape(classifications,
                                             [-1,
                                              shape[1],
                                              shape[2],
                                              self.num_anchors[i],
                                              (self.num_classes + 1)])
                self.location.append(locations)
                self.classification.append(classifications)
        self._setup()
        self.feature_maps = feature_maps
        # return predictions

    def _setup(self):
        """Define ops that load pre-trained vgg16 net's weights and biases and add them to tf.GraphKeys.INIT_OP
        collection.
        """

        # caffe-tensorflow/convert.py can only run with Python2. Since the default encoding format of Python2 is ASCII
        # but the default encoding format of Python3 is UTF-8, it will raise an error without 'encoding="latin1"'
        weight_dict = np.load(self.vgg16_path, encoding="latin1").item()

        scopes = ['conv1_1', 'conv1_2', 'conv2_1', 'conv2_2', 'conv3_1', 'conv3_2', 'conv3_3',
                  'conv4_1', 'conv4_2', 'conv4_3', 'conv5_1', 'conv5_2', 'conv5_3']
        for scope in scopes:
            with tf.variable_scope(scope.split('_')[0] + '/' + scope, reuse=True):
                weights = tf.get_variable('weights')
                biases = tf.get_variable('biases')
                w_init_op = weights.assign(weight_dict[scope]['weights'])
                b_init_op = biases.assign(weight_dict[scope]['biases'])
                tf.add_to_collection(tf.GraphKeys.INIT_OP, w_init_op)
                tf.add_to_collection(tf.GraphKeys.INIT_OP, b_init_op)

        with tf.variable_scope('fc6', reuse=True):
            weights = tf.get_variable('weights')
            biases = tf.get_variable('biases')
            w = weight_dict['fc6']['weights']
            b = weight_dict['fc6']['biases']
            w = np.reshape(w, (7, 7, 512, 4096))
            w = w[0:-1:2, 0:-1:2, :, 0:-1:4]
            b = b[0:-1:4]
            w_init_op = weights.assign(w)
            b_init_op = biases.assign(b)
            tf.add_to_collection(tf.GraphKeys.INIT_OP, w_init_op)
            tf.add_to_collection(tf.GraphKeys.INIT_OP, b_init_op)

        with tf.variable_scope('fc7', reuse=True):
            weights = tf.get_variable('weights')
            biases = tf.get_variable('biases')
            w = weight_dict['fc7']['weights']
            b = weight_dict['fc7']['biases']
            w = np.reshape(w, (1, 1, 4096, 4096))
            w = w[:, :, 0:-1:4, 0:-1:4]
            b = b[0:-1:4]
            w_init_op = weights.assign(w)
            b_init_op = biases.assign(b)
            tf.add_to_collection(tf.GraphKeys.INIT_OP, w_init_op)
            tf.add_to_collection(tf.GraphKeys.INIT_OP, b_init_op)

    def add_summary(self):
        for i, feature_map in enumerate(self.feature_maps):
            tf.summary.histogram('feature_map_%d' % i,  feature_map)
        with tf.variable_scope(tf.get_variable_scope(), reuse=True):
            v = tf.get_variable('l2_norm/gamma')
            tf.summary.scalar('gamma_mean', tf.reduce_mean(v))

    def get_loss(self, gloc, gcls, scope):
        self._ssd_loss(gloc, gcls)
        loss = tf.get_collection(tf.GraphKeys.LOSSES, scope=scope) + \
               tf.get_collection(tf.GraphKeys.REGULARIZATION_LOSSES, scope=scope)
        loss = tf.add_n(loss)
        return loss

def main():
    x = tf.placeholder(shape=[None, 300, 300, 3], dtype=tf.float32)
    net = vgg16_ssd()
    net.build(x)
    net.get_loss()




if __name__ == '__main__':
    main()