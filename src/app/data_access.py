from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.tools import tool


class ShoppingDataStore:
    """Student scaffold for mock-data lookup."""

    def __init__(self, json_path: Path) -> None:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        self.metadata = data.get("metadata", {})
        self.customers = data.get("customers", [])
        self.orders = data.get("orders", [])
        self.vouchers = data.get("vouchers", [])

        self.customer_by_id = {c["customer_id"]: c for c in self.customers}
        self.order_by_id = {o["order_id"]: o for o in self.orders}
        
        self.orders_by_customer_id = {}
        for o in self.orders:
            cid = o.get("customer_id")
            if cid:
                self.orders_by_customer_id.setdefault(cid, []).append(o)
        
        # Sort orders by created_at descending
        for cid in self.orders_by_customer_id:
            self.orders_by_customer_id[cid].sort(key=lambda x: x.get("created_at", ""), reverse=True)

        self.vouchers_by_customer_id = {}
        for v in self.vouchers:
            cid = v.get("customer_id")
            if cid:
                self.vouchers_by_customer_id.setdefault(cid, []).append(v)

    def get_customer_by_id(self, customer_id: str) -> dict[str, Any]:
        customer = self.customer_by_id.get(customer_id)
        if customer:
            return {"status": "ok", "customer": customer}
        return {"status": "not_found", "customer_id": customer_id}

    def get_orders_by_customer_id(self, customer_id: str, limit: int = 10) -> dict[str, Any]:
        orders = self.orders_by_customer_id.get(customer_id)
        if orders:
            return {"status": "ok", "orders": orders[:limit]}
        return {"status": "not_found", "customer_id": customer_id}

    def get_order_detail_by_order_id(self, order_id: str) -> dict[str, Any]:
        order = self.order_by_id.get(order_id)
        if order:
            return {"status": "ok", "order": order}
        return {"status": "not_found", "order_id": order_id}

    def get_vouchers_by_customer_id(
        self,
        customer_id: str,
        only_active: bool = False,
    ) -> dict[str, Any]:
        vouchers = self.vouchers_by_customer_id.get(customer_id)
        if not vouchers:
            return {"status": "not_found", "customer_id": customer_id}
            
        if only_active:
            vouchers = [v for v in vouchers if v.get("status") == "active" and v.get("remaining_uses", 0) > 0]
            
        return {"status": "ok", "vouchers": vouchers}


def build_data_tools(store: ShoppingDataStore) -> list:
    @tool
    def get_customer_by_id(customer_id: str) -> dict[str, Any]:
        """Lấy thông tin khách hàng bằng customer_id."""
        return store.get_customer_by_id(customer_id)

    @tool
    def get_orders_by_customer_id(customer_id: str, limit: int = 10) -> dict[str, Any]:
        """Lấy danh sách các đơn hàng gần đây của khách hàng bằng customer_id."""
        return store.get_orders_by_customer_id(customer_id, limit)

    @tool
    def get_order_detail_by_order_id(order_id: str) -> dict[str, Any]:
        """Lấy chi tiết một đơn hàng cụ thể bằng order_id. Thông tin này bao gồm trạng thái đơn, thời gian giao, và sản phẩm."""
        return store.get_order_detail_by_order_id(order_id)

    @tool
    def get_vouchers_by_customer_id(customer_id: str, only_active: bool = False) -> dict[str, Any]:
        """Lấy danh sách voucher của một khách hàng bằng customer_id. Nếu only_active=True, chỉ lấy các voucher đang hoạt động và còn lượt sử dụng."""
        return store.get_vouchers_by_customer_id(customer_id, only_active)

    return [
        get_customer_by_id,
        get_orders_by_customer_id,
        get_order_detail_by_order_id,
        get_vouchers_by_customer_id,
    ]
