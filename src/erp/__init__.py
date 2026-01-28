"""
ERP-specific MCP configurations and tools.

Provides specialized functionality for:
- SAP S/4HANA
- Microsoft Dynamics 365
- Oracle ERP Cloud
- NetSuite
- Workday
"""

from .dynamics365 import Dynamics365Tools
from .sap_s4hana import SAPS4HANATools

__all__ = [
    "Dynamics365Tools",
    "SAPS4HANATools",
]
