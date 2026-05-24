# Telegram Delivery Acknowledgment Implementation Plan

1. Add failing backend tests for safe settings, acknowledgment responses,
   token-redacted errors, and endpoint validation.
2. Implement `backend/telegram_delivery.py` and
   `POST /api/telegram-delivery`.
3. Add failing frontend tests for delivery-state display.
4. Add an explicit Live Observatory **Send Telegram** action with status.
5. Document configuration and the explicit-send workflow.
6. Run Python/frontend gates and browser verification.
7. Send one labeled test message through the real configured bot, record the
   acknowledgment without credentials, then PR and merge.
