import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from agent_dir.agent import Agent
from environment import Environment
from torch.distributions import Categorical
import matplotlib.pyplot as plt

class PolicyNet(nn.Module):
    def __init__(self, state_dim, action_num, hidden_dim):
        super(PolicyNet, self).__init__()
        self.fc1 = nn.Linear(state_dim, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, action_num)

    def forward(self, x):
        x = F.relu(self.fc1(x))
        x = self.fc2(x)
        action_prob = F.softmax(x, dim=1)
        return action_prob

class AgentPG(Agent):
    def __init__(self, env, args):
        self.env = env
        self.model = PolicyNet(state_dim = self.env.observation_space.shape[0],
                               action_num= self.env.action_space.n,
                               hidden_dim=64)
       
        if args.test_pg:
            self.load('pg.cpt')
        # discounted reward
        self.gamma = 0.99 
        
        # training hyperparameters
        self.num_episodes = 5000 # total training episodes (actually too large...)
        self.display_freq = 10 # frequency to display training progress
        
        # optimizer
        self.optimizer = torch.optim.Adam(self.model.parameters(), lr=3e-3)
        
        # saved rewards and actions
        self.rewards, self.saved_actions = [], []
        self.saved_log_probs=[]
        
    
    
    def save(self, save_path):
        print('save model to', save_path)
        torch.save(self.model.state_dict(), save_path)
    
    def load(self, load_path):
        print('load model from', load_path)
        self.model.load_state_dict(torch.load(load_path))

    def init_game_setting(self):
        self.rewards, self.saved_actions = [], []

    def make_action(self, state, test=False):
        # TODO:
        # Use your model to output distribution over actions and sample from it.
        # HINT: google torch.distributions.Categorical
        
        state = torch.from_numpy(state).float().unsqueeze(0)
        probs = self.model(state)
        m = Categorical(probs)
        action = m.sample()
        
        self.saved_log_probs.append(m.log_prob(action))
        return action.item()

    def update(self):
        # TODO:
        # discount your saved reward
        R=0
        loss = []
        returns = []
        
        for r in self.rewards[::-1]:
            R = r + self.gamma * R
            returns.insert(0, R)
        returns = torch.tensor(returns)
        returns = (returns - returns.mean()) / (returns.std() +np.finfo(np.float32).eps)
        # TODO:
        # compute loss
        for log_prob, R in zip(self.saved_log_probs, returns):
            loss.append(-log_prob * R)
       
        self.optimizer.zero_grad()
        loss = torch.cat(loss).sum()
        loss.backward(retain_graph=True)
        self.optimizer.step()
        del self.rewards[:]
        del self.saved_log_probs[:]

    def train(self):
        avg_reward = None # moving average of reward
        time_step=0 # setting time 
        totol_traning_step=100000
        res=[]
        steps=[]
        for epoch in range(self.num_episodes):
            state = self.env.reset()
            self.init_game_setting()
            done = False
            while(not done):
                action = self.make_action(state)
                state, reward, done, _ = self.env.step(action)
                
                
                self.saved_actions.append(action)
                self.rewards.append(reward)
                time_step+=1
                steps.append(time_step)

            # for logging 
            last_reward = np.sum(self.rewards)
            avg_reward = last_reward if not avg_reward else avg_reward * 0.9 + last_reward * 0.1
            res.append(avg_reward)
            # update model
            self.update()

            if epoch % self.display_freq == 0: # display_freq =10
                print('Epochs: %d/%d | Avg reward: %f '%
                       (epoch, self.num_episodes, avg_reward))
            
            if avg_reward > 100: # to pass baseline, avg. reward > 50 is enough.
                self.save('pg.cpt')
                break
        
        plt.plot(res)
        plt.ylabel('Moving average ep reward')
        plt.xlabel('Step')
        plt.show()
            
            