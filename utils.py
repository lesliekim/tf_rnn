import os
import pickle
import random
import numpy as np
import re
import cv2 as cv

param_file = open('param.txt','r')
param = param_file.read()
pattern = re.compile(r'height:\s*\d+', re.M)
match = pattern.findall(param)
if match:
    norm_height = int(match[0].split(':')[1])
else:
    sys.exit('image height is not defined in param.txt!')

param_file.close()

def load_set(datadir, dataname):
    filename = os.path.join(datadir, dataname + '_image.p')
    print('Loading data from: ' + filename)
    f = open(filename, 'rb')
    seqImage = pickle.load(f)
    f.close()

    filename = os.path.join(datadir, dataname + '_label.p')
    print('Loading label from: ' + filename)
    f = open(filename, 'rb')
    seqLabel = pickle.load(f)
    f.close()
    return seqImage, seqLabel
def sparse_tuple_from(sequences, dtype=np.int32):
    indices = []
    values = []

    for i, seq in enumerate(sequences):
        #print('seq len: ',len(seq))
        #print(seq)
        indices.extend(zip([i] * len(seq), xrange(len(seq))))
        values.extend(seq)
        #print('values len: ', len(values))
    
    indices = np.asarray(indices, dtype=np.int64)
    values = np.asarray(values, dtype=dtype)
    shape = np.asarray([len(sequences), np.asarray(indices).max(0)[1] + 1], dtype=np.int64)
    return indices, values, shape
def get_row(sparse_tuple, row, dtype=np.int32):
    optlist = []
    cnt = 0
    for pos in sparse_tuple[0]:
        if pos[0] == row:
            optlist.append(sparse_tuple[1][cnt])
        cnt += 1
    return optlist

class Loader(object):
    def __init__(self, datadir, set_list = [], batch_size = 1):
        self.count = 0
        self.batch_size = batch_size
        self.norm_height = norm_height
        print('Data Loader initializing ...')
        self.image = []
        self.label = []
        for dataset in set_list:
            print('Set ' + dataset + '...')
            tmpImage, tmpLabel = load_set(datadir, dataset)
            self.image += tmpImage
            self.label += tmpLabel
        self.train_length = len(self.label)
        self.batch_number = int(np.ceil(np.float(self.train_length) / np.float(batch_size)))
        
        self.target_len = 0
        for target in self.label:
            self.target_len += len(target)

    def next_batch(self):
        if self.count + self.batch_size < self.train_length:
            x_batch_seq = self.image[self.count : self.count + self.batch_size]
            y_batch_seq = self.label[self.count : self.count + self.batch_size]
            self.count += self.batch_size
        else:
            x_batch_seq = self.image[self.count :]
            y_batch_seq = self.label[self.count :]
            self.count = 0

        step_batch = np.zeros(shape=[len(x_batch_seq)], dtype='int64')
        for i in xrange(len(step_batch)):
            step_batch[i] = np.shape(x_batch_seq[i])[1]
        x_batch = np.zeros(shape=[len(step_batch), np.max(step_batch), self.norm_height, 1])
        print x_batch.shape
        for i in xrange(len(step_batch)):
            x_batch[i, :step_batch[i], :, 0] = np.transpose(x_batch_seq[i][np.newaxis, :, :], (0, 2, 1))

        # Creating sparse representation to feed the placeholder
        #print(y_batch_seq)
        y_batch = sparse_tuple_from(y_batch_seq)
        tar_len_batch = 0
        for y in y_batch_seq:
            tar_len_batch += len(y)
        return x_batch / 255., y_batch, step_batch, tar_len_batch

    def shuffle(self):
        compact = zip(self.image, self.label)
        random.shuffle(compact)
        self.image, self.label = map(list, zip(*compact))
'''
train_loader = Loader('../psl_data/244Images/traindata', ['inputfile_0'], 16, 32)
x_train, y_train, step_batch, tar_len_batch = train_loader.next_batch()
print('x_train: ', np.shape(x_train))
print('y_train: ', np.shape(y_train))
print('step_batch: ', np.shape(step_batch))
print('tar_len_batch: ', np.shape(tar_len_batch))
'''
def read_probfile(filename):
    with open(filename, 'r') as f:
        prob = [float(x[:-1]) for x in f]
    return prob

def move_padding(prob, padding=0.189871):# default value 0.189871 comes from really network output on padding
    N = len(prob)
    end = N - 1
    for i in xrange(N - 1, -1, -1):
        if prob[i] == padding:
            end = i
    return prob[:end]

def local_min(prob, threshold=0, bg=1.0, fg=0.0):
    N = len(prob)
    if N < 2:
        raise ValueError('prob length should > 1!')

    peak = [bg] * N
    for i in xrange(N):
        if i > 0 and i < N - 1:
            if prob[i] < prob[i - 1] and prob[i] < prob[i + 1]:
                peak[i] = prob[i]
            elif i == 0:
                if prob[i] < prob[i + 1]:
                    peak[i] = prob[i]
            else:
                if prob[i] < prob[i - 1]:
                    peak[i] = prob[i]

    if threshold:
        for i in xrange(N):
            if peak[i] > threshold:
                peak[i] = bg # noise point, set to background value
            else:
                peak[i] = fg # local min

    return peak

def prob_to_pos(prob, pooling_size=1, bg=1.0, fg=0.0): # we assume your stride size is equal to your pooling size
    n_prob = move_padding(prob)
    peak = local_min(n_prob, 0.02)
    N = len(peak)
    pos = [bg] * (pooling_size * N)
    if pooling_size > 1:
        count = 0
        for i in xrange(N):
            for j in xrange(pooling_size):
                pos[count] = peak[i]
                count += 1
    else:
        pos = peak[:]

    return pos

def draw_pos_on_image(pos, img, img_name, fg=0.0):
    height, width = img.shape[:2]
    N = len(pos)
    if abs(N - width) > 2:
        raise ValueError('ctc prob length and image width are not match: prob length: %d, image width: %d' % (N, width))

    f_img = cv.cvtColor(np.cast['uint8'](img), cv.COLOR_GRAY2BGR)
    
    for i in xrange(N):
        if pos[i] == fg and i < width:
            cv.line(f_img, (i, 0), (i, height - 1), (0,0,255))
    
    cv.imwrite(img_name, f_img)
        

