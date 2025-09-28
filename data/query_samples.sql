-- 1. How many customers were created each quarter in the last 2 years?

SELECT DATE_TRUNC('quarter', created_at) AS quarter, COUNT(*) AS customers
FROM customers
WHERE created_at >= CURRENT_DATE - INTERVAL '2 years'
GROUP BY quarter
ORDER BY quarter;


-- 2. Which branch cities have more than 50 employees? (HAVING clause)

SELECT city, COUNT(e.id) AS employee_count
FROM branches b
JOIN employees e ON e.branch_id = b.id
GROUP BY city
HAVING COUNT(e.id) > 50;


-- 3. Which accounts never had any transfers (sent or received)? (NOT EXISTS)

SELECT a.id, a.account_number
FROM accounts a
WHERE NOT EXISTS (
    SELECT 1 FROM transfers t
    WHERE t.from_account = a.id OR t.to_account = a.id
);


-- 4. What is the median sale amount overall? (percentile_cont window function)

SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY total_amount) AS median_sale
FROM sales
WHERE status = 'completed';


-- 5. Which products had sales in every quarter of the last year? (relational division style)

WITH quarters AS (
    SELECT DISTINCT DATE_TRUNC('quarter', sale_time) AS q
    FROM sales
    WHERE sale_time >= CURRENT_DATE - INTERVAL '1 year'
),
product_quarters AS (
    SELECT product_id, DATE_TRUNC('quarter', sale_time) AS q
    FROM sales
    WHERE sale_time >= CURRENT_DATE - INTERVAL '1 year'
    GROUP BY product_id, q
)
SELECT p.name
FROM products p
JOIN product_quarters pq ON p.id = pq.product_id
GROUP BY p.id, p.name
HAVING COUNT(DISTINCT pq.q) = (SELECT COUNT(*) FROM quarters);


-- 6. Who are the top 5 customers by total transfers sent, and what percent of all transfer volume do they contribute? (window function + ratio)

WITH total_volume AS (
    SELECT SUM(amount) AS total FROM transfers
)
SELECT c.id, c.first_name, c.last_name,
       SUM(t.amount) AS sent_amount,
       SUM(t.amount) / (SELECT total FROM total_volume) * 100 AS pct_of_total
FROM customers c
JOIN accounts a ON a.customer_id = c.id
JOIN transfers t ON t.from_account = a.id
GROUP BY c.id, c.first_name, c.last_name
ORDER BY sent_amount DESC
LIMIT 5;


-- 7. Which employees were hired before their branch was created? (correlated join on dates)

SELECT e.id, e.first_name, e.last_name, b.name AS branch_name
FROM employees e
JOIN branches b ON e.branch_id = b.id
WHERE e.hired_at < b.created_at;


-- 8. What are the top 10 merchants by refund ratio (refund amount / sales amount)?

SELECT m.name,
       SUM(r.amount) / NULLIF(SUM(s.total_amount),0) AS refund_ratio
FROM merchants m
JOIN sales s ON s.merchant_id = m.id
LEFT JOIN refunds r ON r.sale_id = s.id
GROUP BY m.id, m.name
ORDER BY refund_ratio DESC
LIMIT 10;


-- 9. What is the running cumulative sales amount per month? (window cumulative sum)

SELECT DATE_TRUNC('month', sale_time) AS month,
       SUM(total_amount) AS monthly_sales,
       SUM(SUM(total_amount)) OVER (ORDER BY DATE_TRUNC('month', sale_time)) AS cumulative_sales
FROM sales
GROUP BY month
ORDER BY month;


-- 10. Which accounts have balances more than double the average balance of their account type?

SELECT a.id, a.account_number, a.balance, a.account_type
FROM accounts a
JOIN (
    SELECT account_type, AVG(balance) AS avg_bal
    FROM accounts
    GROUP BY account_type
) avg_t ON a.account_type = avg_t.account_type
WHERE a.balance > 2 * avg_t.avg_bal;


-- 11. Which categories have declining average sale amount over the last 3 months? (lag window function)

WITH monthly_avg AS (
    SELECT p.category,
           DATE_TRUNC('month', s.sale_time) AS month,
           AVG(s.total_amount) AS avg_sale
    FROM sales s
    JOIN products p ON s.product_id = p.id
    WHERE s.sale_time >= CURRENT_DATE - INTERVAL '3 months'
    GROUP BY p.category, month
)
SELECT category
FROM (
    SELECT category, month, avg_sale,
           LAG(avg_sale) OVER (PARTITION BY category ORDER BY month) AS prev_avg
    FROM monthly_avg
) t
WHERE prev_avg IS NOT NULL AND avg_sale < prev_avg
GROUP BY category;


-- 12. Which customers bought products from at least 5 distinct categories? (COUNT DISTINCT HAVING)

SELECT c.id, c.first_name, c.last_name, COUNT(DISTINCT p.category) AS category_count
FROM customers c
JOIN sales s ON s.customer_id = c.id
JOIN products p ON p.id = s.product_id
GROUP BY c.id, c.first_name, c.last_name
HAVING COUNT(DISTINCT p.category) >= 5;


-- 13. What are the most common refund reasons, ranked with percentages?

WITH total AS (SELECT COUNT(*)::decimal AS n FROM refunds)
SELECT reason, COUNT(*) AS cnt,
       COUNT(*) / (SELECT n FROM total) * 100 AS pct
FROM refunds
GROUP BY reason
ORDER BY cnt DESC;


-- 14. List all pairs of customers that transferred money between each other. (self-join style)

SELECT DISTINCT c1.id AS sender_id, c2.id AS receiver_id
FROM transfers t
JOIN accounts a1 ON t.from_account = a1.id
JOIN accounts a2 ON t.to_account = a2.id
JOIN customers c1 ON a1.customer_id = c1.id
JOIN customers c2 ON a2.customer_id = c2.id
WHERE c1.id <> c2.id;


-- 15. Which merchant has the widest geographic reach (most distinct customer cities)?

SELECT m.name, COUNT(DISTINCT b.city) AS cities
FROM merchants m
JOIN sales s ON s.merchant_id = m.id
JOIN customers c ON s.customer_id = c.id
JOIN accounts a ON a.id = s.account_id
JOIN branches b ON b.id IN (
    SELECT e.branch_id FROM employees e
)
GROUP BY m.id, m.name
ORDER BY cities DESC
LIMIT 1;


-- 16. Which accounts had both failed and successful transfers? (INTERSECT)

SELECT from_account AS account_id FROM transfers WHERE status = 'completed'
INTERSECT
SELECT from_account AS account_id FROM transfers WHERE status = 'failed';


-- 17. Which products have the highest price but never sold? (anti-join)

SELECT p.name, p.price
FROM products p
LEFT JOIN sales s ON s.product_id = p.id
WHERE s.id IS NULL
ORDER BY p.price DESC
LIMIT 10;


-- 18. For each merchant, find the earliest and latest sale time. (MIN/MAX aggregation)

SELECT m.name, MIN(s.sale_time) AS first_sale, MAX(s.sale_time) AS last_sale
FROM merchants m
JOIN sales s ON s.merchant_id = m.id
GROUP BY m.id, m.name;


-- 19. Which audit logs mention the word 'fraud' in details JSON? (JSONB query)

SELECT id, entity_type, action, performed_at, details
FROM audit_logs
WHERE details::text ILIKE '%fraud%';


-- 20. What is the 90th percentile of transfer amounts by status?

SELECT status,
       PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY amount) AS p90_amount
FROM transfers
GROUP BY status;