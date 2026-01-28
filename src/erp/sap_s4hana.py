"""
SAP S/4HANA ERP Tools
Provides SAP S/4HANA-specific MCP tools and queries.
"""

from typing import Any, Dict, List, Optional
from mcp.types import Tool


class SAPS4HANATools:
    """
    SAP S/4HANA-specific tools for MCP.
    
    Provides ERP functionality:
    - Financial reporting (FI/CO)
    - Sales & Distribution (SD)
    - Materials Management (MM)
    - Production Planning (PP)
    - CDS View access
    """
    
    @staticmethod
    def get_tools() -> List[Tool]:
        """Return SAP S/4HANA-specific tools."""
        return [
            Tool(
                name="get_financial_summary",
                description="Get financial summary from SAP FI module",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "company_code": {
                            "type": "string",
                            "description": "SAP Company Code"
                        },
                        "fiscal_year": {
                            "type": "string",
                            "description": "Fiscal year (YYYY)"
                        },
                        "fiscal_period": {
                            "type": "string",
                            "description": "Fiscal period (optional)"
                        }
                    },
                    "required": ["company_code", "fiscal_year"]
                }
            ),
            Tool(
                name="get_sales_orders",
                description="Get sales order overview from SAP SD module",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "sales_org": {
                            "type": "string",
                            "description": "Sales Organization"
                        },
                        "customer": {
                            "type": "string",
                            "description": "Customer number (optional)"
                        },
                        "date_from": {
                            "type": "string",
                            "description": "Date from (YYYY-MM-DD)"
                        },
                        "date_to": {
                            "type": "string",
                            "description": "Date to (YYYY-MM-DD)"
                        }
                    },
                    "required": ["sales_org"]
                }
            ),
            Tool(
                name="get_inventory_overview",
                description="Get material inventory overview from SAP MM module",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "plant": {
                            "type": "string",
                            "description": "Plant code"
                        },
                        "material": {
                            "type": "string",
                            "description": "Material number (optional)"
                        },
                        "material_group": {
                            "type": "string",
                            "description": "Material group (optional)"
                        }
                    },
                    "required": ["plant"]
                }
            ),
            Tool(
                name="get_production_orders",
                description="Get production order status from SAP PP module",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "plant": {
                            "type": "string",
                            "description": "Plant code"
                        },
                        "status": {
                            "type": "string",
                            "description": "Order status: CRTD, REL, CNF, TECO"
                        },
                        "date_from": {
                            "type": "string",
                            "description": "Scheduled start from"
                        }
                    },
                    "required": ["plant"]
                }
            ),
            Tool(
                name="list_cds_views",
                description="List available CDS views for analytics",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "pattern": {
                            "type": "string",
                            "description": "View name pattern (e.g., 'I_Sales*')"
                        },
                        "module": {
                            "type": "string",
                            "description": "Module filter: FI, CO, SD, MM, PP"
                        }
                    }
                }
            ),
            Tool(
                name="get_vendor_performance",
                description="Get vendor/supplier performance metrics",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "vendor": {
                            "type": "string",
                            "description": "Vendor number (optional)"
                        },
                        "purchasing_org": {
                            "type": "string",
                            "description": "Purchasing organization"
                        },
                        "date_from": {
                            "type": "string",
                            "description": "Date from (YYYY-MM-DD)"
                        }
                    },
                    "required": ["purchasing_org"]
                }
            ),
            Tool(
                name="get_cost_center_report",
                description="Get cost center actual vs plan from SAP CO",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "controlling_area": {
                            "type": "string",
                            "description": "Controlling area"
                        },
                        "cost_center": {
                            "type": "string",
                            "description": "Cost center (optional)"
                        },
                        "fiscal_year": {
                            "type": "string",
                            "description": "Fiscal year"
                        }
                    },
                    "required": ["controlling_area", "fiscal_year"]
                }
            ),
        ]
    
    @staticmethod
    def get_financial_summary_query(
        company_code: str,
        fiscal_year: str,
        fiscal_period: Optional[str] = None
    ) -> str:
        """Generate financial summary query using CDS views."""
        period_filter = f"AND fiscalperiod = '{fiscal_period}'" if fiscal_period else ""
        
        return f"""
        -- SAP S/4HANA Financial Summary using CDS View
        SELECT 
            companycode,
            fiscalyear,
            fiscalperiod,
            glaccount,
            glaccountname,
            SUM(amountincompanycodecurrency) as amount,
            companycodecurrency,
            debitcreditcode
        FROM I_GLACCOUNTLINEITEM
        WHERE companycode = '{company_code}'
        AND fiscalyear = '{fiscal_year}'
        {period_filter}
        GROUP BY 
            companycode, fiscalyear, fiscalperiod,
            glaccount, glaccountname,
            companycodecurrency, debitcreditcode
        ORDER BY glaccount
        """
    
    @staticmethod
    def get_sales_orders_query(
        sales_org: str,
        customer: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> str:
        """Generate sales orders query using CDS views."""
        filters = [f"salesorganization = '{sales_org}'"]
        
        if customer:
            filters.append(f"soldtoparty = '{customer}'")
        if date_from:
            filters.append(f"salesordercreationdate >= '{date_from}'")
        if date_to:
            filters.append(f"salesordercreationdate <= '{date_to}'")
        
        where_clause = " AND ".join(filters)
        
        return f"""
        -- SAP S/4HANA Sales Orders using CDS View
        SELECT 
            salesorder,
            salesordertype,
            salesorganization,
            distributionchannel,
            soldtoparty,
            soldtopartyname,
            salesordercreationdate,
            requesteddeliverydate,
            overallsdprocessstatus,
            totalnetamount,
            transactioncurrency
        FROM I_SALESORDER
        WHERE {where_clause}
        ORDER BY salesordercreationdate DESC
        LIMIT 1000
        """
    
    @staticmethod
    def get_inventory_overview_query(
        plant: str,
        material: Optional[str] = None,
        material_group: Optional[str] = None
    ) -> str:
        """Generate inventory overview query."""
        filters = [f"plant = '{plant}'"]
        
        if material:
            filters.append(f"material = '{material}'")
        if material_group:
            filters.append(f"materialgroup = '{material_group}'")
        
        where_clause = " AND ".join(filters)
        
        return f"""
        -- SAP S/4HANA Material Stock Overview
        SELECT 
            material,
            materialname,
            plant,
            storagelocation,
            materialgroup,
            materialtype,
            SUM(matlwrhsestkqtyinmatlbaseunit) as total_stock,
            baseunit,
            SUM(valuatedstocktotalvalue) as stock_value,
            currency
        FROM I_MATERIALSTOCKBYWRHSE
        WHERE {where_clause}
        GROUP BY 
            material, materialname, plant, storagelocation,
            materialgroup, materialtype, baseunit, currency
        ORDER BY material
        """
    
    @staticmethod
    def get_production_orders_query(
        plant: str,
        status: Optional[str] = None,
        date_from: Optional[str] = None
    ) -> str:
        """Generate production orders query."""
        filters = [f"productionplant = '{plant}'"]
        
        if status:
            filters.append(f"manufacturingorderstatus = '{status}'")
        if date_from:
            filters.append(f"mfgorderscheduledstartdate >= '{date_from}'")
        
        where_clause = " AND ".join(filters)
        
        return f"""
        -- SAP S/4HANA Production Orders
        SELECT 
            manufacturingorder,
            manufacturingordertype,
            material,
            productionplant,
            manufacturingorderstatus,
            totalquantity,
            manufacturingorderunit,
            mfgorderscheduledstartdate,
            mfgorderscheduledenddate,
            mfgorderactualreleasedate
        FROM I_MANUFACTURINGORDER
        WHERE {where_clause}
        ORDER BY mfgorderscheduledstartdate DESC
        LIMIT 500
        """
    
    @staticmethod
    def get_cds_views_query(pattern: Optional[str] = None, module: Optional[str] = None) -> str:
        """List available CDS views."""
        filters = []
        
        if pattern:
            filters.append(f"VIEW_NAME LIKE '{pattern.replace('*', '%')}'")
        
        # Map modules to common CDS view prefixes
        module_prefixes = {
            "FI": ("I_GLACCOUNT%", "I_JOURNAL%", "I_FINANCIAL%"),
            "CO": ("I_COSTCENTER%", "I_PROFITCENTER%", "I_CONTROLLING%"),
            "SD": ("I_SALES%", "I_CUSTOMER%", "I_BILLING%"),
            "MM": ("I_MATERIAL%", "I_PURCHAS%", "I_SUPPLIER%"),
            "PP": ("I_MANUFACTURING%", "I_PRODUCTION%", "I_WORKORDER%"),
        }
        
        if module and module.upper() in module_prefixes:
            prefixes = module_prefixes[module.upper()]
            prefix_conditions = " OR ".join([f"VIEW_NAME LIKE '{p}'" for p in prefixes])
            filters.append(f"({prefix_conditions})")
        
        where_clause = " AND ".join(filters) if filters else "1=1"
        
        return f"""
        -- List CDS Views
        SELECT 
            VIEW_NAME,
            SCHEMA_NAME,
            VIEW_TYPE,
            IS_VALID,
            CREATE_TIME
        FROM VIEWS
        WHERE VIEW_TYPE = 'CALC'
        AND {where_clause}
        ORDER BY VIEW_NAME
        LIMIT 100
        """
    
    @staticmethod
    def get_cost_center_report_query(
        controlling_area: str,
        fiscal_year: str,
        cost_center: Optional[str] = None
    ) -> str:
        """Generate cost center actual vs plan report."""
        cc_filter = f"AND costcenter = '{cost_center}'" if cost_center else ""
        
        return f"""
        -- SAP S/4HANA Cost Center Actual vs Plan
        SELECT 
            controllingarea,
            costcenter,
            costcentername,
            costelement,
            costelementname,
            fiscalyear,
            SUM(CASE WHEN valuetype = '010' THEN amountincontrollingareacurrency ELSE 0 END) as actual_amount,
            SUM(CASE WHEN valuetype = '020' THEN amountincontrollingareacurrency ELSE 0 END) as plan_amount,
            controllingareacurrency
        FROM I_COSTCENTERACTUALDATA
        WHERE controllingarea = '{controlling_area}'
        AND fiscalyear = '{fiscal_year}'
        {cc_filter}
        GROUP BY 
            controllingarea, costcenter, costcentername,
            costelement, costelementname, fiscalyear,
            controllingareacurrency
        ORDER BY costcenter, costelement
        """
