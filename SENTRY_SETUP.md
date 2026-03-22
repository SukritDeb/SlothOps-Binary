# SlothOps Sentry Setup Guide

If you are the developer building the target application (e.g., the Node.js/Express app), follow these instructions to stream your application crashes directly into the SlothOps Engine.

---

## 1. Add Sentry to your App

First, make sure you have an account on [Sentry.io](https://sentry.io/) and have created a new Project (select Node.js/Express). 

Install the Sentry SDK in your application:
```bash
npm install @sentry/node @sentry/profiling-node
```

Initialize Sentry as early as possible in your `index.js` or `app.ts` file:
```javascript
import * as Sentry from "@sentry/node";
import { nodeProfilingIntegration } from "@sentry/profiling-node";

Sentry.init({
  dsn: "YOUR_SENTRY_DSN_HERE", // Get this from your Sentry Project Settings
  integrations: [
    nodeProfilingIntegration(),
  ],
  // TracesSampleRate is set to 1.0 to capture 100% of transactions for performance monitoring.
  tracesSampleRate: 1.0, 
  profilesSampleRate: 1.0,
});
```

*For an Express app, make sure to add the Sentry error handler middleware as the very last middleware right before app.listen!*
```javascript
Sentry.setupExpressErrorHandler(app);
```

---

## 2. Expose the SlothOps Engine (Local Testing)

The SlothOps engine runs locally on port `8000` (`http://localhost:8000`). Sentry.io is on the internet, so it cannot send webhooks to your `localhost`.

To solve this, use `ngrok` to create a secure tunnel:
```bash
# In a new terminal window
ngrok http 8000
```

Ngrok will print a Forwarding URL that looks like `https://a1b2c3d4.ngrok.app`. 
**Copy this URL.**

*(Note: Keep ngrok running. If you restart it on the free tier, the URL will change and you'll need to update Sentry).*

---

## 3. Configure the Sentry Webhook

Now, we need to tell Sentry to send all errors from your app to that ngrok URL.

1. Go to your **Sentry.io Dashboard**.
2. Click **Settings** (gear icon) -> **Integrations**.
3. Search for **Webhooks** and click Add/Install.
4. In the Webhook Configuration URL field, paste your ngrok URL and append `/webhook/sentry` to it.
   - Example: `https://a1b2c3d4.ngrok.app/webhook/sentry`
5. Save the configuration.

---

## 4. Test It

1. Start the **SlothOps Engine** (`uvicorn main:app --reload --port 8000`).
2. Start your **Target App**.
3. Trigger an error in your app (e.g., hit an endpoint that throws a `TypeError`).
4. Look at the SlothOps Engine terminal — you should immediately see it receive the webhook, parse the stack trace, and try to fix the bug!

You're done! SlothOps is now watching your application. 🦥
