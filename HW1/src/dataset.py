import random
import torch
from torch.utils.data import Dataset


class DialogDataset(Dataset):
    """
    Args:
        data (list): List of samples.
        padding (int): Index used to pad sequences to the same length.
        n_negative (int): Number of false options used as negative samples to
            train. Set to -1 to use all false options.
        n_positive (int): Number of true options used as positive samples to
            train. Set to -1 to use all true options.
        shuffle (bool): Do not shuffle options when sampling.
            **SHOULD BE FALSE WHEN TESTING**
    """
    def __init__(self, data, padding=0,
                 n_negative=99, n_positive=1,
                 context_padded_len=400, option_padded_len=60, shuffle=True):
        self.data = data
        self.n_positive = n_positive
        self.n_negative = n_negative
        self.context_padded_len = context_padded_len
        self.option_padded_len = option_padded_len
        self.padding = padding
        self.shuffle = shuffle

    def __len__(self):
        return len(self.data)

    def __getitem__(self, index):
        data = dict(self.data[index])
        positives = data['options'][:data['n_corrects']]#正確答案 0~n_corrects
        negatives = data['options'][data['n_corrects']:]#錯誤答案 n_corrects~end
        positive_ids = data['option_ids'][:data['n_corrects']]#正確答案 id
        negative_ids = data['option_ids'][data['n_corrects']:]#錯誤答案 id

        if self.n_positive == -1:
            n_positive = len(positives)
        if self.n_negative == -1:
            n_negative = len(negatives)
        else:
            n_positive = min(len(positives), self.n_positive)
            n_negative = min(len(negatives), self.n_negative)

        # TODO: sample positive indices
        positive_indices = [i for i in range(n_positive)]
        #positive_indices =[0]
        # TODO: sample negative indices
        negative_indices = [i for i in range(n_negative)]
        #negative_indices=[i for i in range(1,100)]
        # collect sampled options
        data['options'] = (
            [positives[i] for i in positive_indices]
            + [negatives[i] for i in negative_indices]
        )
        data['option_ids'] = (
            [positive_ids[i] for i in positive_indices]
            + [negative_ids[i] for i in negative_indices]
        )
        data['labels'] = [1] * n_positive + [0] * n_negative # ex. [1] * 2 + [0] * 3= [1, 1, 0, 0, 0]

        # use the last one utterance because RNN
        # change not last
        # import pdb; pdb.set_trace()
        # data['context'] = data['context'][-1]
        # if len(data['context']) > self.context_padded_len:
        #     data['context'] = data['context'][:self.context_padded_len]
        
        
        #取all
       
        
        data['context']=[x for j in data['context'] for x in j]
        if len(data['context']) > self.context_padded_len:
            data['context'] = data['context'][:self.context_padded_len]


        return data

    def collate_fn(self, datas): # 分批次
        batch = {}

        # collate lists
        batch['id'] = [data['id'] for data in datas]
        batch['speaker'] = [data['speaker'] for data in datas]
        batch['labels'] = torch.tensor([data['labels'] for data in datas])
        batch['option_ids'] = [data['option_ids'] for data in datas]

        # build tensor of context
        batch['context_lens'] = [len(data['context']) for data in datas]
        padded_len = min(self.context_padded_len, max(batch['context_lens']))
        batch['context'] = torch.tensor(
            [pad_to_len(data['context'], padded_len, self.padding)
             for data in datas]
        )

        # build tensor of options
        batch['option_lens'] = [
            [min(max(len(opt), 1), self.option_padded_len)
             for opt in data['options']]
            for data in datas]
        padded_len = min(
            self.option_padded_len,
            max(sum(batch['option_lens'], []))
        )
        batch['options'] = torch.tensor(
            [[pad_to_len(opt, padded_len, self.padding)
              for opt in data['options']]
             for data in datas]
        )

        return batch


def pad_to_len(arr, padded_len, padding=0):
    """ Pad `arr` to `padded_len` with padding if `len(arr) < padded_len`.
    If `len(arr) > padded_len`, truncate arr to `padded_len`.
    Example:
        pad_to_len([1, 2, 3], 5, -1) == [1, 2, 3, -1, -1]
        pad_to_len([1, 2, 3, 4, 5, 6], 5, -1) == [1, 2, 3, 4, 5]
    Args:
        arr (list): List of int.
        padded_len (int)
        padding (int): Integer used to pad.
    """
    # TODO
    while(len(arr)!=padded_len):
        if len(arr) < padded_len:
            arr.append(padding)    
        else:
            arr.pop()
    return arr
            
