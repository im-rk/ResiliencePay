$ErrorActionPreference = "Stop"

Write-Host "Creating branch..."
git checkout -b feature/security-and-rls

Write-Host "Commit 1..."
git add apps/api/src/middleware/webhook_auth.py services/observe/webhook_lock.py packages/config/settings.py packages/config/redis_client.py
git commit -m "feat: add webhook auth middleware and lock service"

Write-Host "Commit 2..."
git add apps/api/src/routers/webhooks.py apps/api/src/main.py
git commit -m "feat: implement webhook router and integrate"

Write-Host "Commit 3..."
git add apps/api/tests/test_webhook_auth.py services/observe/tests/test_webhook_lock.py
git commit -m "test: add webhook security and idempotency tests"

Write-Host "Commit 4..."
git add enable_rls.py
git commit -m "feat: add script to enable RLS on all public tables"

Write-Host "Pushing branch..."
git push -u origin feature/security-and-rls

Write-Host "Done!"
