from math import ceil
import math
from explainers.MaskingModelExplainer import MaskingModelExplainer
import tensorflow as tf
import tensorflow.python.keras as keras
from tensorflow.keras.layers import Input, Dense, Add, Multiply, BatchNormalization, Attention
from utils.utils import focal_loss
import numpy as np


class TabularMM(MaskingModelExplainer):

    def __init__(self, predict_fn, in_shape, optimizer=tf.keras.optimizers.RMSprop()):
        super(TabularMM, self).__init__(predict_fn)
        self.MASKGEN, self.MASKAPPLY, self.PATCH = self.buildExplanator(predict_fn, in_shape)
        self.optimizer = optimizer

    def definePatch(self, in_shape):
        """
        Define the model that produce the patch from the original image
        :param in_shape: input shape
        :return:
        """

        # Mette insieme maskapply e maskgen
        img = keras.Input(shape=in_shape)
        MASKGEN = self.defineMaskGen(in_shape)
        MASKAPPLY = self.defineMaskApply(in_shape)
        mask = MASKGEN(img)
        patch = MASKAPPLY([img, mask[0], mask[1]])
        #patch = MASKAPPLY([img, mask])
        # Generatore patch - Applicatore della patch - Modello completo (gen+app)
        return MASKGEN, MASKAPPLY, keras.Model(inputs=img, outputs=patch)
    


    # to do
    
    def defineMaskGen(self, in_shape):
        """
            Define the model that produce the patch from the original image
            :param in_shape: input shape
            :return:
        """
        inputs = Input(in_shape)
        x0 = Dense(128)(inputs)
        x0 = Dense(64)(x0)
        x0 = Dense(128)(x0)
        outputs = Dense(in_shape)(x0)

        x1 = Dense(128, activation='relu')(inputs)
        x1 = Dense(64, activation='relu')(x1)
        x1 = Dense(128, activation='relu')(x1)
        outputs_c = Dense(in_shape, activation='sigmoid')(x1)


        return keras.Model(inputs=inputs, outputs=[outputs, outputs_c], name='MaskGen')

    '''
    def defineMaskGen(self, in_shape):
        inputs = Input(in_shape)
        x0 = Attention()([inputs,inputs])
        #x0 = Dense(32)(x0)
        x0 = keras.layers.BatchNormalization()(x0)
        outputs = Dense(in_shape)(x0)

        #x1 = Dense(64, activation='relu')(x1)
        x1 = Attention()([inputs,inputs])
        x1 = keras.layers.BatchNormalization()(x1)
        outputs_c = Dense(in_shape, activation='relu')(x1)
        #outputs_c = keras.layers.BatchNormalization()(x1)

        return keras.Model(inputs=inputs, outputs=[outputs, outputs_c], name='MaskGen')
    '''


    '''
    def defineMaskApply(self, in_shape):
        inputs = [Input(in_shape, name='input_img'), Input(in_shape, name='input_mask'),
                  Input(in_shape, name='input_choice')]  # Sample, Mask
        mid_output = Multiply()(inputs[1:])
        outputs = Add()([inputs[0], mid_output])

        outputs = Add()([inputs[0], inputs[0]])


        return keras.Model(inputs=inputs, outputs=outputs)
    '''
    
    def defineMaskApply(self, in_shape):
        inputs = [Input(in_shape, name='input_img'), Input(in_shape, name='input_mask'),
                  Input(in_shape, name='input_choice')]  # Sample, Mask
        mid_output = Multiply()(inputs[1:])
        outputs = Add()([inputs[0], mid_output])


        return keras.Model(inputs=inputs, outputs=outputs)
    

    # to do
    def fit_explanator(self, train_images_expl, train_labels_expl, epochs=1, verbose=False,
                       batch_size=32, loss_weights=None):

        binary_ce = tf.keras.losses.BinaryCrossentropy(reduction=tf.keras.losses.Reduction.NONE)

        data_a = train_images_expl[train_labels_expl == 1]
        data_n = train_images_expl[train_labels_expl == 0]
        for epoch in range(epochs):
            for i in range(ceil(train_images_expl[train_labels_expl == 1].shape[0] / batch_size)):

                batch_n = data_n
                batch_a = data_a[i * batch_size:min((i + 1) * batch_size, data_a.shape[0])]

                with tf.GradientTape() as tape:
                    masks, choose = self.MASKGEN(batch_a)
                    patches = self.MASKAPPLY([batch_a, masks, choose])
                    classification = self.model(patches)

                    #classification = self.model(batch_a)

                    # Sparsity
                    sparsity = tf.math.sqrt(masks ** 2)
                    sparsity = tf.reduce_sum(sparsity, axis=1)

                    # Reduce the number of samples
                    #ndim_loss = binary_ce(y_true=np.zeros_like(choose), y_pred=choose)focal_loss
                    ndim_loss = focal_loss(y_true=np.zeros_like(choose), y_pred=choose)

                    # Classification error
                    cross_entropy = focal_loss(y_pred=classification, y_true=np.zeros_like(classification))

                    # Distance from normal data
                    differences = patches[:, tf.newaxis, :] - batch_n[np.newaxis, : , :]
                    differences = differences ** 2
                    sample_distance = tf.reduce_mean(tf.sqrt(tf.reduce_sum(differences, axis=-1)), axis=1)


                    loss = tf.reduce_mean(loss_weights[0] * cross_entropy +
                                          loss_weights[1] * sample_distance +
                                          loss_weights[2] * sparsity +
                                          loss_weights[3] * ndim_loss)

                    if verbose:
                        tf.print(f'Loss: {loss}, Model:{tf.reduce_mean(cross_entropy)}, '
                                 f'Dist: {tf.reduce_mean(sample_distance)}, 'f'Sparsity: {tf.reduce_mean(sparsity)}',
                                 f'Dim choise: {tf.reduce_mean(ndim_loss)}')

                model_vars = self.PATCH.trainable_variables
                gradients = tape.gradient(loss, model_vars)
                self.optimizer.apply_gradients(zip(gradients, model_vars))

    
    
    def return_explanation(self, in_shape, sample, threshold):
        sample = np.array(sample).reshape((1, -1))
        mask, choose = self.MASKGEN(sample)
        sum = 0
        
        for i in range(choose.shape[1]):
            sum = sum + choose[0][i].numpy()
        sum = sum  / choose.shape[1]
        choose = tf.where(choose > sum, choose, 0)
        patches = self.MASKAPPLY([sample, mask, choose])

        return patches.numpy(), choose.numpy()


