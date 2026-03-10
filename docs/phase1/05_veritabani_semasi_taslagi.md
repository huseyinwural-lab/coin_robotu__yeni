# Veritabanı Şeması Taslağı (PostgreSQL)

## users
- id (PK, uuid-string)
- email (unique)
- password_hash
- role (admin/user)
- is_active
- created_at

## bot_profiles
- id (PK)
- user_id (FK -> users.id)
- name
- exchange
- market_type
- symbols (JSON)
- strategy_type
- timeframe (default 15m)
- trend_timeframe (default 1h)
- leverage
- is_enabled
- created_at, updated_at

## risk_policies
- id (PK)
- user_id (FK -> users.id)
- name
- position_size_pct
- atr_stop_multiplier
- risk_reward_ratio
- daily_loss_cutoff_pct
- max_open_positions
- max_leverage
- spread_limit_bps
- slippage_limit_bps
- min_liquidity_usdt
- created_at, updated_at

## strategy_templates
- id (PK)
- name (unique)
- strategy_type
- parameters (JSON)
- is_active
- created_by (FK -> users.id)
- created_at, updated_at

## execution_events
- id (PK)
- bot_profile_id (FK -> bot_profiles.id)
- exchange
- symbol
- side
- quantity
- mock_price
- execution_status
- response_payload (JSON)
- note
- created_at

## audit_logs
- id (PK)
- actor_user_id
- actor_role
- action
- entity_type
- entity_id
- severity
- details (JSON)
- created_at
