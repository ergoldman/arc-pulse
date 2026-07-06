#!/usr/bin/env python3
"""
Manual test push — bypasses ALL timing/condition logic and sends a single
test notification to every current subscriber, right now. Use this to verify
end-to-end delivery (jsonbin -> GitHub Action -> Apple/Google push -> device)
without waiting for a real closing/opening/holiday trigger to happen.

Run via the "Send Test Notification" workflow (manual trigger only).
"""
import json, os, sys
from send_notifications import get_subscriptions, send_push

def main():
    subs_raw = get_subscriptions()
    print(f"{len(subs_raw)} subscribers found.")
    if not subs_raw:
        print("No subscribers — nothing to test. Make sure you've clicked "
              "'Notify me' on the site first.")
        return

    sent, failed = 0, 0
    for entry in subs_raw:
        sub = entry.get("sub", entry)  # support both old and new storage shapes
        ok = send_push(
            sub,
            title="ARC Pulse test",
            body="If you're seeing this, notifications are working! 🎉",
            tag="test-push",
        )
        if ok:
            sent += 1
        else:
            failed += 1

    print(f"Test push result: {sent} succeeded, {failed} failed, out of {len(subs_raw)} total.")

if __name__ == "__main__":
    main()
