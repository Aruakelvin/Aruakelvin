"""Cross-chain DeFi incentive analyzer."""

__version__ = "0.1.0"

from .analyzer import Analyzer, Filters, ScanResult, summarize  # noqa: E402
from .models import Category, Opportunity, RewardToken  # noqa: E402

__all__ = ["Analyzer", "Filters", "ScanResult", "summarize", "Category", "Opportunity", "RewardToken", "__version__"]
