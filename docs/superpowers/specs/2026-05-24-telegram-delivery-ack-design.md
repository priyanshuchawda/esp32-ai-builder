# Telegram Delivery Acknowledgment Design

## Goal

Allow an operator to send the already visible Observatory prepared message to
the configured Telegram chat and see whether Telegram accepted it.

## API Contract

`POST /api/telegram-delivery` accepts:

- `message`: the prepared, displayed text, limited to 500 characters;
- `event_signature`: the compact evidence identifier currently on screen.

It returns:

- `status`: `sent`, `failed`, or `not_configured`;
- `event_signature`;
- `message_id` only after a successful Telegram acknowledgment;
- `destination`: masked chat suffix only;
- safe `detail` for non-success states.

## Security And Behavior

- Credentials are loaded locally from ignored environment files.
- Bot tokens and full chat IDs never appear in responses or logs.
- Sending is explicit from the Live Observatory UI; there is no browser-side
  automatic alert loop.
- The endpoint sends only the trust-gated message already shown to the
  operator.

## Validation

- Unit-test missing configuration, successful Telegram acknowledgement, and
  HTTP failure without token leakage.
- Unit-test the FastAPI endpoint with a stub sender.
- Add frontend formatting/state tests and browser verification.
- After tests pass, deliberately send one live validation message to the
  configured chat and verify Telegram returns a message ID.
