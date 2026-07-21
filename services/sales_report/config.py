"""
Sales report configuration models for client-specific SQUAD presentations.
Defines the customer profile, tooling selection, cost assumptions, and
asset paths needed to generate a complete sales presentation.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# -- Cost assumption defaults (industry averages) --
DEFAULT_MACHINE_RATE_PER_HOUR: float = 170.0
DEFAULT_LABOR_COST_PER_HOUR: float = 10.0
DEFAULT_PART_COST_INJECTION: float = 0.5
DEFAULT_PART_COST_STAMPING: float = 5.0


@dataclass
class ToolConfig:
    """
    Configuration for a single tooling ID included in the report.
    Holds the equipment code plus optional overrides for cost and commodity type.
    """

    equipment_code: str
    commodity: str = "Injection"
    part_cost: Optional[float] = None
    cavities: Optional[int] = None
    contracted_ct_seconds: Optional[float] = None

    def resolved_part_cost(self) -> float:
        """Return explicit part cost or commodity-based default."""
        if self.part_cost is not None:
            return self.part_cost
        if self.commodity.lower() == "stamping":
            return DEFAULT_PART_COST_STAMPING
        return DEFAULT_PART_COST_INJECTION


@dataclass
class BusinessRecommendation:
    """
    Manual input from sales team for the recommendation slide.
    Contains the ask amount, scope, and expected savings.
    """

    ask_amount: float = 0.0
    supplier_count: int = 0
    tool_count: int = 0
    tools_per_supplier: int = 100
    expected_saving: float = 0.0
    notes: List[str] = field(default_factory=list)


@dataclass
class ClientAssets:
    """
    Paths to client-specific branding assets (logos, backgrounds, photos).
    All paths are relative to the assets/clients/<client_slug>/ directory.
    """

    cover_image: str = ""
    client_logo: str = ""
    emoldino_logo: str = "emoldino_logo.png"
    team_photos_dir: str = "team"
    background_dark: str = ""
    background_light: str = ""


@dataclass
class SalesReportConfig:
    """
    Top-level configuration for a SQUAD sales presentation.
    Combines client metadata, selected tools, cost assumptions,
    date range, and optional business recommendations.
    """

    # -- Client identification --
    client_name: str = "Client"
    client_slug: str = "client"
    presentation_title: str = "SQUAD Presentation"

    # -- Date range for analyses --
    start_date: str = ""
    end_date: str = ""
    report_month: str = ""

    # -- Tooling selection --
    tools: List[ToolConfig] = field(default_factory=list)

    # -- Cost assumptions --
    machine_rate_per_hour: float = DEFAULT_MACHINE_RATE_PER_HOUR
    labor_cost_per_hour: float = DEFAULT_LABOR_COST_PER_HOUR
    project_cost: float = 11709.0

    # -- Business recommendations (manual input from sales) --
    recommendations: Optional[BusinessRecommendation] = None

    # -- Asset paths --
    assets: ClientAssets = field(default_factory=ClientAssets)

    # -- ROI scaling tiers for executive summary --
    roi_tiers: Dict[int, str] = field(
        default_factory=lambda: {
            1000: "1,000 Toolings",
            5000: "5,000 Toolings",
            10000: "10,000 Toolings",
        }
    )

    # -- Screenshot placeholders (paths filled in after manual capture) --
    screenshot_paths: Dict[str, str] = field(default_factory=dict)

    @property
    def equipment_codes(self) -> List[str]:
        """Extract all equipment codes from tool configs."""
        return [t.equipment_code for t in self.tools]

    @property
    def total_cost_per_hour(self) -> float:
        """Combined machine rate + labor cost per hour."""
        return self.machine_rate_per_hour + self.labor_cost_per_hour

    @property
    def assets_base_dir(self) -> str:
        """Base directory for this client's assets."""
        return f"assets/clients/{self.client_slug}"
