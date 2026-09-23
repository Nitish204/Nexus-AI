import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getPushSubscriptionStatus, isPushSupported } from "./push";

describe("isPushSupported", () => {
  const originalServiceWorker = navigator.serviceWorker;
  const originalPushManager = window.PushManager;

  afterEach(() => {
    Object.defineProperty(navigator, "serviceWorker", { value: originalServiceWorker, configurable: true });
    window.PushManager = originalPushManager;
  });

  it("returns false when the browser has neither API", () => {
    delete navigator.serviceWorker;
    delete window.PushManager;
    expect(isPushSupported()).toBe(false);
  });

  it("returns true when both serviceWorker and PushManager exist", () => {
    Object.defineProperty(navigator, "serviceWorker", { value: {}, configurable: true });
    window.PushManager = function () {};
    expect(isPushSupported()).toBe(true);
  });
});

describe("getPushSubscriptionStatus", () => {
  const originalServiceWorker = navigator.serviceWorker;
  const originalPushManager = window.PushManager;
  const originalNotification = window.Notification;

  beforeEach(() => {
    window.PushManager = function () {};
  });

  afterEach(() => {
    Object.defineProperty(navigator, "serviceWorker", { value: originalServiceWorker, configurable: true });
    window.PushManager = originalPushManager;
    window.Notification = originalNotification;
  });

  it("reports 'unsupported' when push isn't supported at all", async () => {
    delete navigator.serviceWorker;
    expect(await getPushSubscriptionStatus()).toBe("unsupported");
  });

  it("reports 'denied' when notification permission was denied", async () => {
    Object.defineProperty(navigator, "serviceWorker", { value: {}, configurable: true });
    window.Notification = { permission: "denied" };
    expect(await getPushSubscriptionStatus()).toBe("denied");
  });

  it("reports 'not-subscribed' when there is no service worker registration yet", async () => {
    window.Notification = { permission: "default" };
    Object.defineProperty(navigator, "serviceWorker", {
      value: { getRegistration: vi.fn().mockResolvedValue(undefined) },
      configurable: true,
    });
    expect(await getPushSubscriptionStatus()).toBe("not-subscribed");
  });

  it("reports 'subscribed' when a push subscription already exists", async () => {
    window.Notification = { permission: "granted" };
    const registration = {
      pushManager: { getSubscription: vi.fn().mockResolvedValue({ endpoint: "https://example.com" }) },
    };
    Object.defineProperty(navigator, "serviceWorker", {
      value: { getRegistration: vi.fn().mockResolvedValue(registration) },
      configurable: true,
    });
    expect(await getPushSubscriptionStatus()).toBe("subscribed");
  });
});
