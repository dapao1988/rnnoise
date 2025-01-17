#!/usr/bin/python

from __future__ import print_function

import os
import sys
import tensorflow as tf
import tensorflow.keras as K
import matplotlib.pyplot as plt
#from tensorflow import keras as K

#from keras.models import Sequential
from tensorflow.keras.models import Sequential
from tensorflow.keras.models import Model
from tensorflow.keras.layers import Input
from tensorflow.keras.layers import Dense
from tensorflow.keras.layers import LSTM
from tensorflow.keras.layers import GRU
from tensorflow.keras.layers import SimpleRNN
from tensorflow.keras.layers import Dropout
from tensorflow.keras.layers import concatenate
from tensorflow.keras import losses
from tensorflow.keras import regularizers
from tensorflow.keras.constraints import min_max_norm
from tensorflow.keras.callbacks import ModelCheckpoint
import h5py

from tensorflow.keras.constraints import Constraint
from tensorflow.keras import backend as K
import numpy as np

#import tensorflow as tf
#from keras.backend.tensorflow_backend import set_session
#config = tf.ConfigProto()
#config.gpu_options.per_process_gpu_memory_fraction = 0.42
#set_session(tf.Session(config=config))


def my_crossentropy(y_true, y_pred):
    return K.mean(2*K.abs(y_true-0.5) * K.binary_crossentropy(y_pred, y_true), axis=-1)

def mymask(y_true):
    return K.minimum(y_true+1., 1.)

def msse(y_true, y_pred):
    return K.mean(mymask(y_true) * K.square(K.sqrt(y_pred) - K.sqrt(y_true)), axis=-1)

def mycost(y_true, y_pred):
    return K.mean(mymask(y_true) * (10*K.square(K.square(K.sqrt(y_pred) - K.sqrt(y_true))) + K.square(K.sqrt(y_pred) - K.sqrt(y_true)) + 0.01*K.binary_crossentropy(y_pred, y_true)), axis=-1)

def my_accuracy(y_true, y_pred):
    return K.mean(2*K.abs(y_true-0.5) * K.equal(y_true, K.round(y_pred)), axis=-1)

class WeightClip(Constraint):
    '''Clips the weights incident to each hidden unit to be inside a range
    '''
    def __init__(self, c=2):
        self.c = c

    def __call__(self, p):
        return K.clip(p, -self.c, self.c)

    def get_config(self):
        return {'name': self.__class__.__name__,
            'c': self.c}

if '__main__' == __name__:
    if len(sys.argv) < 2:
        save_dir = '.' # 当前目录
    else:
        save_dir = sys.argv[1]
        print("model save path:{}".format(os.path.abspath('.') ))

    reg = 0.000001
    constraint = WeightClip(0.499)

    print('Build model...')
    main_input = Input(shape=(None, 42), name='main_input')
    tmp = Dense(24, activation='tanh', name='input_dense', kernel_constraint=constraint, bias_constraint=constraint)(main_input)
    vad_gru = GRU(24, activation='tanh', recurrent_activation='sigmoid', return_sequences=True, name='vad_gru', kernel_regularizer=regularizers.l2(reg), recurrent_regularizer=regularizers.l2(reg), kernel_constraint=constraint, recurrent_constraint=constraint, bias_constraint=constraint, reset_after=False)(tmp)
    vad_output = Dense(1, activation='sigmoid', name='vad_output', kernel_constraint=constraint, bias_constraint=constraint)(vad_gru)
    noise_input = tf.keras.layers.concatenate([tmp, vad_gru, main_input])
    noise_gru = GRU(48, activation='relu', recurrent_activation='sigmoid', return_sequences=True, name='noise_gru', kernel_regularizer=regularizers.l2(reg), recurrent_regularizer=regularizers.l2(reg), kernel_constraint=constraint, recurrent_constraint=constraint, bias_constraint=constraint, reset_after=False)(noise_input)
    denoise_input = tf.keras.layers.concatenate([vad_gru, noise_gru, main_input])

    denoise_gru = GRU(96, activation='tanh', recurrent_activation='sigmoid', return_sequences=True, name='denoise_gru', kernel_regularizer=regularizers.l2(reg), recurrent_regularizer=regularizers.l2(reg), kernel_constraint=constraint, recurrent_constraint=constraint, bias_constraint=constraint, reset_after=False)(denoise_input)

    denoise_output = Dense(22, activation='sigmoid', name='denoise_output', kernel_constraint=constraint, bias_constraint=constraint)(denoise_gru)

    model = Model(inputs=main_input, outputs=[denoise_output, vad_output])

    model.compile(loss=[mycost, my_crossentropy],
                  metrics=[msse],
                  optimizer='adam', loss_weights=[10, 0.5])

    checkpointer = ModelCheckpoint(os.path.join(save_dir, 'model_weights.{epoch:02d}-{val_loss:.2f}.hdf5'),
                                               verbose=1, save_weights_only=False, mode='min', save_best_only=True)

    batch_size = 128 #32

    print('Loading data...')
    with h5py.File('training.h5', 'r') as hf:
        all_data = hf['data'][:]
    print('done.')

    window_size = 2000

    nb_sequences = len(all_data)//window_size
    print(nb_sequences, ' sequences')
    x_train = all_data[:nb_sequences*window_size, :42]
    x_train = np.reshape(x_train, (nb_sequences, window_size, 42))

    y_train = np.copy(all_data[:nb_sequences*window_size, 42:64])
    y_train = np.reshape(y_train, (nb_sequences, window_size, 22))

    noise_train = np.copy(all_data[:nb_sequences*window_size, 64:86])
    noise_train = np.reshape(noise_train, (nb_sequences, window_size, 22))

    vad_train = np.copy(all_data[:nb_sequences*window_size, 86:87])
    vad_train = np.reshape(vad_train, (nb_sequences, window_size, 1))

    all_data = 0;
    #x_train = x_train.astype('float32')
    #y_train = y_train.astype('float32')

    print(len(x_train), 'train sequences. x shape =', x_train.shape, 'y shape = ', y_train.shape)

    print('Train...')
    history = model.fit(x_train, [y_train, vad_train],
              batch_size=batch_size,
              epochs=30,
              validation_split=0.1,
              callbacks=[checkpointer])

    print(history)
    print(type(history))
    print(history.history)
    print(type(history.history))
    # model summary for visualize
    plt.plot(history.history['denoise_output_msse'])
    plt.plot(history.history['val_denoise_output_msse'])
    plt.title('denoise model msse')
    plt.ylabel('denoise msse')
    plt.xlabel('epoch')
    plt.legend(['train','test'], loc='upper left')
    plt.show()

    plt.plot(history.history['loss'])
    plt.plot(history.history['val_loss'])
    plt.title('model total loss')
    plt.ylabel('loss')
    plt.xlabel('epoch')
    plt.legend(['train','test'], loc='upper left')
    plt.show()

    model.save("weights.hdf5")
