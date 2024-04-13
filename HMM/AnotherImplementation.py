import numpy as np
import pandas as pd
import scipy.stats as st
from scipy.io import wavfile
from python_speech_features import mfcc
import os
from scipy.stats import multivariate_normal
from sys import stdout
import matplotlib.pyplot as plt
from sklearn.metrics import confusion_matrix
import itertools

def plot_confusion_matrix(test_labels, classifier_labels, classes,
                          normalize=False,
                          title='Confusion matrix',
                          cmap=plt.cm.Blues):
    plt.figure()

    cm = confusion_matrix(test_labels, classifier_labels)

    """
    This function prints and plots the confusion matrix.
    Normalization can be applied by setting `normalize=True`.
    """
    if normalize:
        cm = cm.astype('float') / cm.sum(axis=1)[:, np.newaxis]
        print("Normalized confusion matrix")
    else:
        print('Confusion matrix, without normalization')

    # title += '\nCCR is = ' + str(CCR(test_labels, classifier_labels))

    print(title)

    print(cm)

    plt.imshow(cm, interpolation='nearest', cmap=cmap)
    plt.title(title)
    plt.colorbar()
    tick_marks = np.arange(len(classes))
    plt.xticks(tick_marks, classes, rotation=45)
    plt.yticks(tick_marks, classes)

    fmt = '.2f' if normalize else 'd'
    thresh = cm.max() / 2.
    for i, j in itertools.product(range(cm.shape[0]), range(cm.shape[1])):
        plt.text(j, i, format(cm[i, j], fmt),
                 horizontalalignment="center",
                 color="white" if cm[i, j] > thresh else "black")

    plt.tight_layout()
    plt.ylabel('True label')
    plt.xlabel('Predicted label')
    plt.show()


np.set_printoptions(threshold=np.inf)

cov_bias = 0.001
cov_bias_init = 0.1
min_log_acc = -1500
log_offset = -700
scale_factor = 10

scale = False
normalize = True

random_mu_init = False
random_cov_init = False


class GMM_HMM:

    def __init__(self, name, n_states, n_mixure_count):
        self.name = name
        self.states_count = n_states
        self.mixture_count = n_mixure_count

        # random transaction probabilities
        self.A = np.ones((n_states, n_states)) / n_states

        # random prior
        self.prior = np.ones(n_states) / n_states

        # uniform mixure coefficients
        self.c = np.ones((n_states, n_mixure_count)) / n_mixure_count

        # input dim
        self.dim_count = None

        # gmm means
        self.mu = None

        # gmm covariances
        self.cov = None

    # ********************************************************************************************

    def init_gmm(self, dataset):

        # set input dimentions
        self.dim_count = dataset[0].shape[1]

        # init mu for gmm
        self.mu = np.random.rand(self.states_count, self.mixture_count, self.dim_count)

        if not random_mu_init:
            for i in range(self.states_count):
                for j in range(self.mixture_count):
                    obs_idx = np.random.choice(np.arange(len(dataset)))
                    time = np.random.choice(np.arange(dataset[obs_idx].shape[0]))
                    self.mu[i][j] = dataset[obs_idx][time]

        # init cov matrix
        self.cov = np.random.rand(self.states_count, self.mixture_count, self.dim_count, self.dim_count)

        if not random_cov_init:
            for i in range(self.states_count):
                for j in range(self.mixture_count):
                    obs_idx = np.random.choice(np.arange(len(dataset)))
                    time = np.random.choice(np.arange(dataset[obs_idx].shape[0]))
                    obs = dataset[obs_idx][time].reshape(-1, 1)
                    self.cov[i][j] = np.diag(np.diag(np.dot(obs, obs.T)) + cov_bias_init)

    # ********************************************************************************************

    def forward_prob(self, observation_prob):

        # time steps
        T = observation_prob.shape[1]

        # forward probablities init
        alpha = min_log_acc * np.ones((self.states_count, T))

        # first time probablity
        for i in range(len(self.prior)):
            self.prior[i] += np.exp(log_offset)
        alpha[:, 0] = np.log(self.prior) + observation_prob[:, 0]

        # forward probablities for other times
        for t in range(1, T):
            for j in range(self.states_count):
                for i in range(self.states_count):
                    log_info = alpha[i, t - 1]
                    log_info += np.log(self.A[i, j] + np.exp(log_offset))
                    log_info += observation_prob[j, t]
                    alpha[j, t] = np.logaddexp(alpha[j, t],
                                               log_info)

        return alpha

    # ********************************************************************************************

    def backward_prob(self, observation_prob):

        # time steps
        T = observation_prob.shape[1]

        # backward probablities init
        beta = min_log_acc * np.ones((self.states_count, T))

        # last time probablity
        beta[:, T - 1] = np.ones(self.states_count)

        beta[:, T - 1] = np.log(beta[:, T - 1])

        # backward probablities for other times
        for t in range(T - 2, -1, -1):
            for i in range(self.states_count):
                for j in range(self.states_count):
                    beta[i, t] = np.logaddexp(beta[i, t],
                                              np.log(self.A[i, j] + np.exp(log_offset)) + observation_prob[
                                                  j, t + 1] + beta[j, t + 1])

        return beta

    # ********************************************************************************************

    def get_observation_prob(self, observation):

        T = observation.shape[0]
        observation_prob = np.zeros((self.states_count, T))

        for i in range(self.states_count):
            for t in range(T):
                prob = min_log_acc
                for j in range(self.mixture_count):
                    chel = np.linalg.cholesky(self.cov[i, j])

                    new_prob = np.log(self.c[i, j] + np.exp(log_offset))
                    new_prob += - np.log((2 * np.pi) ** (self.dim_count / 2))
                    new_prob += - np.log(np.linalg.det(chel) ** 2 + np.exp(log_offset))
                    new_prob += - 0.5 * np.dot((observation[t] - self.mu[i, j]).T,
                                               np.dot(np.linalg.inv(self.cov[i, j]), (observation[t] - self.mu[i, j])))

                    prob = np.logaddexp(prob, new_prob)

                observation_prob[i, t] = prob

        return observation_prob

    # ********************************************************************************************

    def train(self, dataset, stop_diff, belkin):

        print('\n--- Running Training for module "{}" '.format(self.instance_name()))

        if normalize:
            for i in range(len(dataset)):
                dataset[i] = (dataset[i] - np.mean(dataset[i], axis=0)) / np.std(dataset[i], axis=0)

        self.init_gmm(dataset)

        counter = 1

        current_liklihood = 0.001
        accum_liklihood_prev = 0

        data_cov = np.zeros((self.dim_count, self.dim_count))
        for observation in dataset:
            for time_serie in observation:
                data_cov += np.dot(time_serie, time_serie.T)

        while True:

            accum_liklihood_prev = current_liklihood
            current_liklihood = 0

            prior_update = np.zeros(self.states_count)
            A_update = np.zeros((self.states_count, self.states_count))
            mu_update = np.zeros(shape=self.mu.shape)
            c_update = np.zeros(shape=self.c.shape)
            cov_update = np.zeros(shape=self.cov.shape)

            for observation in dataset:

                stdout.write(
                    '\r---------- Iteration : {}'.format(counter))
                stdout.flush()

                T = observation.shape[0]
                obs_prob = self.get_observation_prob(observation)

                alpha = self.forward_prob(obs_prob)
                current_liklihood += np.sum(np.exp(alpha), axis=0)[-1]

                beta = self.backward_prob(obs_prob)
                epsilon = np.zeros((self.states_count, self.states_count, T - 1))

                for t in range(T - 1):

                    accum = min_log_acc

                    for i in range(self.states_count):
                        for j in range(self.states_count):
                            epsilon[i, j, t] = alpha[i, t] + np.log(self.A[i][j] + np.exp(log_offset)) + \
                                               obs_prob[j][t + 1] + beta[
                                                   j, t + 1]
                            accum = np.logaddexp(accum, epsilon[i, j, t])

                    epsilon[:, :, t] -= accum

                gamma = np.zeros((self.states_count, T))
                for t in range(T):
                    gamma[:, t] = alpha[:, t] + beta[:, t]
                    accum = min_log_acc
                    for i in range(len(gamma[:, t])):
                        accum = np.logaddexp(accum, gamma[i, t])
                    gamma_sum = accum
                    gamma[:, t] = gamma[:, t] - gamma_sum

                h = np.zeros((self.states_count, self.mixture_count, T))
                for t in range(T):
                    for i in range(self.states_count):
                        for j in range(self.mixture_count):

                            if obs_prob[i, t] != -np.Inf:

                                chel = np.linalg.cholesky(self.cov[i, j])

                                new_prob = np.log(self.c[i, j] + np.exp(log_offset))
                                new_prob += - np.log((2 * np.pi) ** (self.dim_count / 2))
                                new_prob += - np.log(np.linalg.det(chel) ** 2 + np.exp(log_offset))
                                new_prob += - 0.5 * np.dot((observation[t] - self.mu[i, j]).T,
                                                           np.dot(np.linalg.inv(self.cov[i, j]),
                                                                  (observation[t] - self.mu[i, j])))

                                h[i, j, t] = new_prob
                                h[i, j, t] -= obs_prob[i, t]

                            else:
                                h[i, j, t] = -np.Inf

                temp_A_update = np.zeros((self.states_count, self.states_count))
                for i in range(self.states_count):
                    for j in range(self.states_count):

                        accum = min_log_acc
                        for jj in range(self.states_count):
                            for tt in range(T - 1):
                                accum = np.logaddexp(accum, epsilon[i, jj, tt])
                        eps_sum = accum

                        accum = min_log_acc
                        for tt in range(T - 1):
                            accum = np.logaddexp(accum, epsilon[i, j, tt])

                        temp_A_update[i, j] = accum - eps_sum

                temp_A_update = np.exp(temp_A_update)

                if belkin:
                    extra_prob = np.zeros(self.states_count)

                    for i in range(self.states_count):
                        if i != self.states_count - 1:
                            extra_prob[i] = 1 - temp_A_update[i, i] - temp_A_update[i, i + 1]

                    for i in range(self.states_count):
                        for j in range(self.states_count):
                            if i == self.states_count - 1 and j == self.states_count - 1:
                                temp_A_update[i, j] = 1
                            elif i == j or j == i + 1:
                                temp_A_update[i, j] = temp_A_update[i, j] / (1 - extra_prob[i])
                            else:
                                temp_A_update[i, j] = 0

                average = np.zeros((self.states_count, self.mixture_count))
                for i in range(self.states_count):
                    for j in range(self.mixture_count):
                        average[i, j] = np.sum(np.exp(gamma[i] + h[i, j]))

                temp_mu_update = np.zeros(shape=self.mu.shape)
                for i in range(self.states_count):
                    for j in range(self.mixture_count):
                        accum = 0
                        for t in range(T):
                            accum += np.exp(gamma[i, t] + h[i, j, t]) * observation[t]
                        temp = average[i, j]
                        temp += (average[i, j] == 0)
                        temp_mu_update[i, j] = accum / temp
                        # mu_update[i, j] = np.dot(gamma[i] * h[i, j], observation) / average[i, j]

                temp_c_update = np.zeros(shape=self.c.shape)
                for i in range(self.states_count):
                    for j in range(self.mixture_count):
                        summation = np.sum(average[i])
                        summation += (summation == 0)
                        temp_c_update[i, j] = average[i, j] / summation

                temp_cov_update = np.zeros(shape=self.cov.shape)
                for i in range(self.states_count):
                    for j in range(self.mixture_count):

                        accum = 0
                        for t in range(T):
                            diff = (observation[t] - temp_mu_update[i, j]).reshape(-1, 1)
                            accum += np.exp(gamma[i, t] + h[i, j, t]) * np.dot(diff, diff.T)

                        average[i, j] += average[i, j] == 0
                        temp_cov_update[i, j] = (accum / average[i, j] + cov_bias * np.eye(self.dim_count))

                prior_update += np.exp(gamma[:, 0])
                A_update += temp_A_update
                mu_update += temp_mu_update
                c_update += temp_c_update
                cov_update += temp_cov_update

            self.prior = prior_update / len(dataset)
            self.A = A_update / len(dataset)
            self.mu = mu_update / len(dataset)
            self.c = c_update / len(dataset)
            self.cov = cov_update / len(dataset)

            counter += 1

            # prevent devide by zero
            current_liklihood += current_liklihood == 0
            if np.abs((accum_liklihood_prev - current_liklihood) / current_liklihood) < stop_diff:
                return

    # ********************************************************************************************

    def likelihood(self, dataset):

        if normalize:
            for i in range(len(dataset)):
                dataset[i] = (dataset[i] - np.mean(dataset[i], axis=0)) / np.std(dataset[i], axis=0)

        output = np.zeros(len(dataset))

        for i, observation in enumerate(dataset):

            obs_prob = self.get_observation_prob(observation)
            alpha = self.forward_prob(obs_prob)
            output[i] = np.sum(np.exp(alpha), axis=0)[-1]

        return output

    # ********************************************************************************************

    def viterbi(self, dataset):

        if normalize:
            for i in range(len(dataset)):
                dataset[i] = (dataset[i] - np.mean(dataset[i], axis=0)) / np.std(dataset[i], axis=0)

        out_prob = list()
        out_path = list()

        for observation in dataset:

            T = observation.shape[0]
            prob_mat = np.zeros((self.states_count, T))

            obs_prob = self.get_observation_prob(observation)

            # initialize
            prob_mat[:, 0] = self.prior * np.exp(obs_prob[:, 0])
            # path[i].append(i)

            # newpath = [[] for _ in range(self.states_count)]
            for t in range(1, T):
                for j in range(self.states_count):
                    (prob, state) = max(
                        [(prob_mat[i, t - 1] * self.A[i, j] * np.exp(obs_prob[j, t]), i) for i in
                         range(self.states_count)])

                    prob_mat[j, t] = prob
                    # print('j {}, state {}, prob {}'.format(j, state, prob))
                    # newpath[j] = path[state] + [j]
            # path = newpath

            (prob, state) = max([(prob_mat[i, T - 1], i) for i in range(self.states_count)])

            out_prob.append(prob)
            # out_path.append(np.array(path[state]))

        return out_prob, out_path


def build_dataset(sound_path='../Dataset/HindiDigits/'):
    files = sorted(os.listdir(sound_path))
    x_train = []
    y_train = []
    x_test = []
    y_test = []
    data = dict()
    n = len(files)
    for i in range(n):
        feature = feature_extractor(sound_path=sound_path + files[i])
        digit = files[i][0]
        if digit not in data.keys():
            data[digit] = []
            x_test.append(feature)
            y_test.append(digit)
        else:
            if np.random.rand() < 0.25:
                x_test.append(feature)
                y_test.append(digit)
            else:
                x_train.append(feature)
                y_train.append(digit)
                data[digit].append(feature)
    return x_train, y_train, x_test, y_test, data

def feature_extractor(sound_path):
    sampling_freq, audio = wavfile.read(sound_path)
    mfcc_features = mfcc(audio, sampling_freq,nfft = 2048,numcep=13,nfilt=13)
    return mfcc_features

x_train, y_train, x_test, y_test, data = build_dataset()

print(x_test)

predictedLables = []


models = {}
predictions ={}

for key in data.keys():
    model = GMM_HMM(key,4,3)
        # feature = np.ndarray(shape=(1, 13))
        # for list_feature in data[key]:
        #         feature = np.vstack((feature, list_feature))
        # feature = np.delete(feature, (0), axis=0)
        # traindata = feature
        # print(traindata.shape)
    model.train(data[key],1,False)
    models[key] = model
    predictions[key] = model.likelihood(x_test)

print(data.keys())
print(y_test)

correct = 0
total = 0
    

for i in range(len(x_test)):
        predict = -int(1e9)
        predict_digit = -1
        for key in data.keys():
            if predictions[key][i] > predict:
                predict = predictions[key][i]
                predict_digit = key
        if predict_digit == y_test[i]:
            correct += 1
        total += 1
        predictedLables.append(predict_digit)

    # for index, row in test.iterrows():
    #     if(index == 0):
    #         continue
    #     if row['digit'] not in testLable.keys():
    #         testLable[row['digit']] = []
    #     digit = row['digit']
    #     row.drop('digit', inplace=True)
    #     testLable[digit].append(row)

    # for key in testLable.keys():
    #     testLable[key] = np.array(testLable[key])

plot_confusion_matrix(y_test,predictedLables,data.keys())
print(correct, total, correct/total)


