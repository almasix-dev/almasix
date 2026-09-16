"""Third-party service credentials (mail ESPs, Slack, Vonage)."""

from almasix.config import env

config = {
    "mailgun": {
        "domain": env("MAILGUN_DOMAIN"),
        "secret": env("MAILGUN_SECRET"),
        "endpoint": env("MAILGUN_ENDPOINT", "api.mailgun.net"),
        "scheme": env("MAILGUN_SCHEME", "https"),
    },
    "postmark": {
        "token": env("POSTMARK_TOKEN"),
    },
    "resend": {
        "key": env("RESEND_KEY"),
    },
    "ses": {
        "key": env("AWS_ACCESS_KEY_ID"),
        "secret": env("AWS_SECRET_ACCESS_KEY"),
        "region": env("AWS_DEFAULT_REGION", "us-east-1"),
    },
    "cloudflare": {
        "api_token": env("CLOUDFLARE_API_TOKEN"),
        "account_id": env("CLOUDFLARE_ACCOUNT_ID"),
    },
    "vonage": {
        "key": env("VONAGE_KEY"),
        "secret": env("VONAGE_SECRET"),
        "sms_from": env("VONAGE_SMS_FROM"),
    },
    "slack": {
        "notifications": {
            "bot_user_oauth_token": env("SLACK_BOT_USER_OAUTH_TOKEN"),
            "channel": env("SLACK_BOT_USER_DEFAULT_CHANNEL"),
        },
    },
}
