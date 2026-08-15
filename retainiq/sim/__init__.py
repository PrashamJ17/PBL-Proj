"""SubSim -- calibrated subscription-churn simulator with ground-truth counterfactuals."""

from retainiq.sim.config import SimConfig
from retainiq.sim.latents import Latents, draw_latents
from retainiq.sim.subsim import SimResult, simulate

__all__ = ["SimConfig", "Latents", "draw_latents", "SimResult", "simulate"]
