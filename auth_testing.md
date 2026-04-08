# Testing Playbook

Step 1: MongoDB Verification
```
mongosh
use <database_name>
db.users.find({role: "admin"}).pretty()
db.users.findOne({role: "admin"}, {password_hash: 1})
```
Verify: bcrypt hash starts with `$2b$`, indexes exist on users.email (unique), login_attempts.identifier, password_reset_tokens.expires_at (TTL).

Step 2: API Testing
```
curl -c cookies.txt -X POST http://localhost:8001/api/auth/login -H "Content-Type: application/json" -d '{"email":"admin@example.com","password":"admin123"}'
cat cookies.txt
curl -b cookies.txt http://localhost:8001/api/auth/me
```

Login should return the user object and set `access_token` + `refresh_token` cookies. The `/me` call should return the same user using those cookies.

Step 3: Strategy Allocation Session Binding Resilience (2026-04-08)
```
# No x-session-device header, Authorization only
curl -X POST https://<preview>/api/auth/login -H "Content-Type: application/json" \
  -d '{"email":"canary.admin@platform.local","password":"CanaryAdmin123!"}'

curl https://<preview>/api/admin/strategy-allocation/summary \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

Verify: response should not fail with `session_device_missing` when token context matches.
Check logs for `auth_device_binding_event` with `session_device_missing_recovered` on `/api/admin/strategy-allocation*`.
