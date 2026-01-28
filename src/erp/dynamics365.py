"""
Microsoft Dynamics 365 ERP Tools
Provides Dynamics 365-specific MCP tools and queries.
"""

from typing import Any, Dict, List, Optional
from mcp.types import Tool


class Dynamics365Tools:
    """
    Dynamics 365-specific tools for MCP.
    
    Provides CRM/ERP functionality:
    - Customer 360 views
    - Sales pipeline analysis
    - Order management queries
    - Financial summaries
    """
    
    @staticmethod
    def get_tools() -> List[Tool]:
        """Return Dynamics 365-specific tools."""
        return [
            Tool(
                name="get_customer_360",
                description="Get comprehensive customer information including contacts, opportunities, and orders",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "account_id": {
                            "type": "string",
                            "description": "Account ID or name"
                        },
                        "include_activities": {
                            "type": "boolean",
                            "default": True
                        }
                    },
                    "required": ["account_id"]
                }
            ),
            Tool(
                name="get_sales_pipeline",
                description="Get sales pipeline summary with opportunities by stage",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "owner_id": {
                            "type": "string",
                            "description": "Filter by owner/salesperson"
                        },
                        "date_range_days": {
                            "type": "integer",
                            "default": 90,
                            "description": "Days to look back"
                        }
                    }
                }
            ),
            Tool(
                name="get_order_summary",
                description="Get order summary with totals and status breakdown",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "customer_id": {
                            "type": "string",
                            "description": "Filter by customer"
                        },
                        "status": {
                            "type": "string",
                            "description": "Filter by status: Active, Submitted, Invoiced"
                        },
                        "date_range_days": {
                            "type": "integer",
                            "default": 30
                        }
                    }
                }
            ),
            Tool(
                name="get_lead_conversion_metrics",
                description="Get lead conversion rates and funnel metrics",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "date_range_days": {
                            "type": "integer",
                            "default": 90
                        },
                        "source": {
                            "type": "string",
                            "description": "Filter by lead source"
                        }
                    }
                }
            ),
            Tool(
                name="get_product_performance",
                description="Get product sales performance metrics",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "product_id": {
                            "type": "string",
                            "description": "Filter by product"
                        },
                        "date_range_days": {
                            "type": "integer",
                            "default": 90
                        }
                    }
                }
            ),
        ]
    
    @staticmethod
    def get_customer_360_query(account_id: str, include_activities: bool = True) -> str:
        """Generate Customer 360 query for Dynamics 365."""
        query = f"""
        -- Customer 360 View for Dynamics 365
        WITH CustomerInfo AS (
            SELECT 
                a.accountid,
                a.name as account_name,
                a.telephone1,
                a.emailaddress1,
                a.address1_city,
                a.address1_stateorprovince,
                a.revenue,
                a.numberofemployees,
                a.industrycode
            FROM account a
            WHERE a.accountid = '{account_id}' OR a.name LIKE '%{account_id}%'
        ),
        CustomerContacts AS (
            SELECT 
                c.parentcustomerid,
                COUNT(*) as contact_count,
                STRING_AGG(c.fullname, ', ') as contacts
            FROM contact c
            WHERE c.parentcustomerid IN (SELECT accountid FROM CustomerInfo)
            GROUP BY c.parentcustomerid
        ),
        CustomerOpportunities AS (
            SELECT 
                o.customerid,
                COUNT(*) as opportunity_count,
                SUM(o.estimatedvalue) as total_pipeline_value,
                SUM(CASE WHEN o.statecode = 1 THEN o.actualvalue ELSE 0 END) as won_value
            FROM opportunity o
            WHERE o.customerid IN (SELECT accountid FROM CustomerInfo)
            GROUP BY o.customerid
        ),
        CustomerOrders AS (
            SELECT 
                so.customerid,
                COUNT(*) as order_count,
                SUM(so.totalamount) as total_order_value
            FROM salesorder so
            WHERE so.customerid IN (SELECT accountid FROM CustomerInfo)
            GROUP BY so.customerid
        )
        SELECT 
            ci.*,
            COALESCE(cc.contact_count, 0) as contact_count,
            cc.contacts,
            COALESCE(co.opportunity_count, 0) as opportunity_count,
            COALESCE(co.total_pipeline_value, 0) as pipeline_value,
            COALESCE(co.won_value, 0) as won_value,
            COALESCE(cord.order_count, 0) as order_count,
            COALESCE(cord.total_order_value, 0) as total_orders
        FROM CustomerInfo ci
        LEFT JOIN CustomerContacts cc ON ci.accountid = cc.parentcustomerid
        LEFT JOIN CustomerOpportunities co ON ci.accountid = co.customerid
        LEFT JOIN CustomerOrders cord ON ci.accountid = cord.customerid
        """
        return query
    
    @staticmethod
    def get_sales_pipeline_query(owner_id: Optional[str] = None, days: int = 90) -> str:
        """Generate sales pipeline query."""
        owner_filter = f"AND o.ownerid = '{owner_id}'" if owner_id else ""
        
        return f"""
        -- Sales Pipeline Summary
        SELECT 
            o.salesstage,
            o.salesstagecode,
            COUNT(*) as opportunity_count,
            SUM(o.estimatedvalue) as total_value,
            AVG(o.estimatedvalue) as avg_deal_size,
            AVG(o.closeprobability) as avg_probability,
            SUM(o.estimatedvalue * o.closeprobability / 100) as weighted_value
        FROM opportunity o
        WHERE o.statecode = 0  -- Open opportunities
        AND o.createdon >= DATEADD(day, -{days}, GETDATE())
        {owner_filter}
        GROUP BY o.salesstage, o.salesstagecode
        ORDER BY o.salesstagecode
        """
    
    @staticmethod
    def get_order_summary_query(
        customer_id: Optional[str] = None,
        status: Optional[str] = None,
        days: int = 30
    ) -> str:
        """Generate order summary query."""
        filters = []
        if customer_id:
            filters.append(f"so.customerid = '{customer_id}'")
        if status:
            filters.append(f"so.statuscode = '{status}'")
        
        where_clause = " AND ".join(filters) if filters else "1=1"
        
        return f"""
        -- Order Summary
        SELECT 
            FORMAT(so.createdon, 'yyyy-MM') as order_month,
            COUNT(*) as order_count,
            SUM(so.totalamount) as total_amount,
            AVG(so.totalamount) as avg_order_value,
            SUM(CASE WHEN so.statuscode = 3 THEN 1 ELSE 0 END) as invoiced_count,
            SUM(CASE WHEN so.statuscode = 3 THEN so.totalamount ELSE 0 END) as invoiced_amount
        FROM salesorder so
        WHERE so.createdon >= DATEADD(day, -{days}, GETDATE())
        AND {where_clause}
        GROUP BY FORMAT(so.createdon, 'yyyy-MM')
        ORDER BY order_month DESC
        """
