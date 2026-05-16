from __future__ import annotations

import random
from typing import Tuple

import numpy as np
import torch

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


class PrioritizedReplayBuffer:
    def __init__(
        self,
        capacity: int = 100000,
        alpha: float = 0.6,
        beta_start: float = 0.4,
        beta_frames: int = 100000,
        eps: float = 1e-6,
    ) -> None:
        self.capacity = capacity
        self.alpha = alpha
        self.beta_start = beta_start
        self.beta_frames = beta_frames
        self.eps = eps
        self.buffer = []
        self.priorities = np.zeros((capacity,), dtype=np.float32)
        self.pos = 0
        self.frame = 1

    def __len__(self) -> int:
        return len(self.buffer)

    def push(self, state: np.ndarray, action: int, reward: float, next_state: np.ndarray, done: bool) -> None:
        max_priority = self.priorities.max() if self.buffer else 1.0
        data = (state, action, reward, next_state, done)
        if len(self.buffer) < self.capacity:
            self.buffer.append(data)
        else:
            self.buffer[self.pos] = data
        self.priorities[self.pos] = max_priority
        self.pos = (self.pos + 1) % self.capacity

    def _beta(self) -> float:
        return min(1.0, self.beta_start + (1.0 - self.beta_start) * (self.frame / max(self.beta_frames, 1)))

    def sample(self, batch_size: int) -> Tuple[torch.Tensor, ...]:
        if len(self.buffer) == 0:
            raise ValueError("Cannot sample from an empty replay buffer.")

        priorities = self.priorities[: len(self.buffer)]
        scaled = np.power(priorities + self.eps, self.alpha)
        probs = scaled / scaled.sum()
        indices = np.random.choice(len(self.buffer), batch_size, p=probs)
        batch = [self.buffer[idx] for idx in indices]
        states, actions, rewards, next_states, dones = zip(*batch)
        beta = self._beta()
        self.frame += 1
        weights = np.power(len(self.buffer) * probs[indices], -beta)
        weights /= weights.max() if weights.max() > 0 else 1.0

        return (
            torch.tensor(np.array(states), dtype=torch.float32, device=DEVICE),
            torch.tensor(actions, dtype=torch.long, device=DEVICE).unsqueeze(1),
            torch.tensor(rewards, dtype=torch.float32, device=DEVICE).unsqueeze(1),
            torch.tensor(np.array(next_states), dtype=torch.float32, device=DEVICE),
            torch.tensor(dones, dtype=torch.float32, device=DEVICE).unsqueeze(1),
            torch.tensor(indices, dtype=torch.long, device=DEVICE),
            torch.tensor(weights, dtype=torch.float32, device=DEVICE).unsqueeze(1),
        )

    def update_priorities(self, indices, priorities) -> None:
        priorities = np.asarray(priorities).reshape(-1)
        for idx, priority in zip(indices, priorities):
            self.priorities[int(idx)] = float(abs(priority)) + self.eps
