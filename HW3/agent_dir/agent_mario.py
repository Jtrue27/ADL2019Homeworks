import torch
from torch.distributions import Categorical
from torch.optim import RMSprop
from torch.nn.utils import clip_grad_norm_

from a2c.environment_a2c import make_vec_envs
from a2c.storage import RolloutStorage
from a2c.actor_critic import ActorCritic
import matplotlib.pyplot as plt
from collections import deque
import os

use_cuda = torch.cuda.is_available()

class AgentMario:
    def __init__(self, env, args):

        # Hyperparameters
        self.lr = 7e-4
        self.gamma = 0.9
        self.hidden_size = 512
        self.update_freq = 5
        self.n_processes = 16
        self.seed = 7122
        self.max_steps = 1e7
        self.grad_norm = 0.5
        self.entropy_weight = 0.05

        #######################    NOTE: You need to implement
        self.recurrent = True # <- ActorCritic._forward_rnn()
        #######################    Please check a2c/actor_critic.py
        
        self.display_freq = 4000
        self.save_freq = 100000
        self.save_dir = './checkpoints/'

        torch.manual_seed(self.seed)
        torch.cuda.manual_seed_all(self.seed)
        if args.test_mario:
            self.load_model('./checkpoints/model.pt')
        self.envs = env
        if self.envs == None: # creating multiple processes
            self.envs = make_vec_envs('SuperMarioBros-v0', self.seed,
                    self.n_processes)
        self.device = torch.device("cuda:0" if use_cuda else "cpu")

        self.obs_shape = self.envs.observation_space.shape
        self.act_shape = self.envs.action_space.n

        self.rollouts = RolloutStorage(self.update_freq, self.n_processes,
                self.obs_shape, self.act_shape, self.hidden_size)  
        self.model = ActorCritic(self.obs_shape, self.act_shape,
                self.hidden_size, self.recurrent).to(self.device)
        self.optimizer = RMSprop(self.model.parameters(), lr=self.lr, 
                eps=1e-5)

        self.hidden = None
        self.init_game_setting()
   
    def _update(self):
        # TODO: Compute returns
        # R_t = reward_t + gamma * R_{t+1}
        
        for step in reversed(range(self.rollouts.returns.size(0))):
            self.rollouts.returns[step-1]=self.rollouts.rewards[step-1]+self.gamma*self.rollouts.returns[step]

        # TODO:
        # Compute actor critic loss (value_loss, action_loss)
        # OPTIONAL: You can also maxmize entropy to encourage exploration
        # loss = value_loss + action_loss (- entropy_weight * entropy)
        obs_shape = self.rollouts.obs.size()[2:]
        action_shape = self.rollouts.actions.size()[-1]
        num_steps, num_processes, _ = self.rollouts.rewards.size()

        values, action_probs, dist_entropy = self.model(
            self.rollouts.obs[:-1].view(-1, *obs_shape),
            self.rollouts.hiddens[0].view(
                -1, self.hidden_size),
            self.rollouts.masks[:-1].view(-1, 1))
        # cator to log action_probs.
        m = Categorical(action_probs)
        action = m.sample()
        action_log_probs=m.log_prob(action)

        values = values.view(num_steps, num_processes, 1)
        action_log_probs = action_log_probs.view(num_steps, num_processes, 1)
        advantages = self.rollouts.returns[:-1] - values
        value_loss = advantages.pow(2).mean()
        action_loss = -(advantages.detach() * action_log_probs).mean()
        loss=value_loss+action_loss
        # Update
        self.optimizer.zero_grad()
        loss.backward()
        clip_grad_norm_(self.model.parameters(), self.grad_norm)
        self.optimizer.step()
        # for step in reversed(range(self.rewards.size(0))):
        #             self.returns[step] = (self.returns[step + 1] * gamma * self.masks[step + 1] + self.rewards[step]) * self.bad_masks[step + 1] + (1 - self.bad_masks[step + 1]) * self.value_preds[step]
        
        # TODO:
        # Clear rollouts after update (RolloutStorage.reset())
        self.rollouts.reset()
        return loss.item()

    def _step(self, obs, hiddens, masks):
        with torch.no_grad():
            # TODO:
            # Sample actions from the output distributions
            # HINT: you can use torch.distributions.Categorical
            # import ipdb; ipdb.set_trace()
            values,probs,hiddens= self.model(obs,hiddens,masks)
            m = Categorical(probs)
            actions = m.sample()

            
        obs, rewards, dones, infos = self.envs.step(actions.cpu().numpy())
        
        # TODO:
        # Store transitions (obs, hiddens, actions, values, rewards, masks)
        # You need to convert arrays to tensors first
        # HINT: masks = (1 - dones)
        obs = torch.from_numpy(obs).to(self.device)
        rewards = torch.from_numpy(rewards).to(self.device)
        masks=torch.from_numpy(1-dones).to(self.device)
        actions=actions.view(actions.size(0),-1)
        rewards=rewards.view(rewards.size(0),-1)
        masks=masks.view(masks.size(0),-1)
        self.rollouts.insert(obs,hiddens,actions,values,rewards,masks)

        
    def train(self):

        print('Start training')
        running_reward = deque(maxlen=10)
        episode_rewards = torch.zeros(self.n_processes, 1).to(self.device)
        total_steps = 0
        
        # Store first observation
        obs = torch.from_numpy(self.envs.reset()).to(self.device)
        
        self.rollouts.obs[0].copy_(obs)
        self.rollouts.to(self.device)
        n_reward=[]
        
        
        while True:
            # Update once every n-steps
            for step in range(self.update_freq):
                
                self._step(
                    self.rollouts.obs[step],
                    self.rollouts.hiddens[step],
                    self.rollouts.masks[step])

                # Calculate episode rewards
                episode_rewards += self.rollouts.rewards[step]
                for r, m in zip(episode_rewards, self.rollouts.masks[step + 1]):
                    if m == 0:
                        running_reward.append(r.item())
                episode_rewards *= self.rollouts.masks[step + 1]
            
            loss = self._update()
            total_steps += self.update_freq * self.n_processes

            # Log & save model
            if len(running_reward) == 0:
                avg_reward = 0
            else:
                avg_reward = sum(running_reward) / len(running_reward)
                n_reward.append(avg_reward)

            if total_steps % self.display_freq == 0:
                print('Steps: %d/%d | Avg reward: %f'%
                        (total_steps, self.max_steps, avg_reward))
            
            if total_steps % self.save_freq == 0:
                self.save_model('model.pt')
            
            if total_steps >= self.max_steps:
                plt.plot(n_reward)
                plt.ylabel('Moving average  reward')
                plt.xlabel('Step')
                plt.savefig('./mario')
                break
                
            

    def save_model(self, filename):
        torch.save(self.model, os.path.join(self.save_dir, filename))

    def load_model(self, path):
        self.model = torch.load(path)

    def init_game_setting(self):
        if self.recurrent:
            self.hidden = torch.zeros(1, self.hidden_size).to(self.device)

    def make_action(self, observation, test=False):
        # TODO: Use you model to choose an action

        self.model.recurrent=False
        values, action_probs, hiddens=self.model(observation,None,None)
        m = Categorical(action_probs)
        actions = m.sample()
        action=actions.item()
        return action
