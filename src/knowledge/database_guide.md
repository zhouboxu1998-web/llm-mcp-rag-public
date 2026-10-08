# 数据库使用说明

内部分析数据库（SQLite，只读）包含四张表。

## 表结构

- customers(id, name, region)：客户信息，region 为所在区域。
- products(id, name, category, price)：产品信息，category 取值包括 Sensor、Inspection、Service。
- orders(id, customer_id, order_date, status)：订单头，customer_id 关联 customers.id。
- order_items(order_id, product_id, quantity)：订单明细，关联 orders.id 和 products.id。

## 常见计算方法

- 订单总金额：数据库中没有直接存储，需要把订单明细中每个产品的 quantity 乘以 products.price 后求和。
- 某客户的订单：通过 orders.customer_id 关联 customers。
- 已付款订单：筛选 orders.status = 'paid'。

## 注意事项

数据库为只读，不支持新增、修改或删除。日期格式为 YYYY-MM-DD。数据库不记录币种、退款和库存信息。
