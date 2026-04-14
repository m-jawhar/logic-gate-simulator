import { expect, test } from "@playwright/test";

test.describe.configure({ mode: "serial" });

function randomSuffix() {
  return Math.random().toString(36).slice(2, 9);
}

function attachRuntimeCollectors(page) {
  const pageErrors = [];
  const apiErrors = [];

  page.on("pageerror", (error) => pageErrors.push(String(error)));
  page.on("response", async (response) => {
    const url = response.url();
    if (!url.includes("/api/") || response.status() < 400) {
      return;
    }

    let body = "";
    try {
      body = await response.text();
    } catch {
      body = "<unavailable>";
    }

    if (
      response.status() === 409 &&
      url.includes("/api/custom-gates/import/") &&
      body.includes("already exists")
    ) {
      return;
    }

    apiErrors.push(`${response.status()} ${url} :: ${body}`);
  });

  return { pageErrors, apiErrors };
}

async function assertNoRuntimeErrors(runtime) {
  expect(runtime.pageErrors, "Browser page errors were detected").toEqual([]);
  expect(runtime.apiErrors, "API HTTP errors were detected").toEqual([]);
}

async function waitForStatusIncludes(page, text, timeout = 12_000) {
  const status = page.locator(".status-bar");
  await status.waitFor({ state: "visible", timeout });

  const started = Date.now();
  while (Date.now() - started < timeout) {
    const value = await status.innerText();
    if (value.includes(text)) {
      return value;
    }
    await page.waitForTimeout(150);
  }

  throw new Error(
    `Timed out waiting for status to include '${text}'. Last value: ${await status.innerText()}`,
  );
}

async function waitForCurrentUser(page, expectedUser, timeout = 12_000) {
  const started = Date.now();
  const expected = expectedUser.toLowerCase();
  const label = page.locator("text=Current User:").first();
  await label.waitFor({ state: "visible", timeout });

  while (Date.now() - started < timeout) {
    const value = (await label.innerText()).toLowerCase();
    if (value.includes(`current user: ${expected}`)) {
      return value;
    }
    await page.waitForTimeout(150);
  }

  throw new Error(
    `Timed out waiting for current user '${expectedUser}'. Last value: ${await label.innerText()}`,
  );
}

async function waitForInputContains(
  page,
  selector,
  fragment,
  timeout = 12_000,
) {
  const input = page.locator(selector);
  await input.waitFor({ state: "visible", timeout });
  const started = Date.now();

  while (Date.now() - started < timeout) {
    const value = await input.inputValue();
    if (value.includes(fragment)) {
      return value;
    }
    await page.waitForTimeout(150);
  }

  throw new Error(
    `Timed out waiting for ${selector} to include '${fragment}'. Last value: ${await input.inputValue()}`,
  );
}

async function waitForWirePaths(page, minimumCount, timeout = 12_000) {
  const started = Date.now();
  while (Date.now() - started < timeout) {
    const count = await page.locator("svg path").count();
    if (count >= minimumCount) {
      return count;
    }
    await page.waitForTimeout(150);
  }
  throw new Error(
    `Timed out waiting for at least ${minimumCount} wire paths. Last count: ${await page.locator("svg path").count()}`,
  );
}

async function gotoPane(page, name) {
  const button = page.locator(".mobile-pane-nav button", { hasText: name });
  await button.click();
  await page.waitForTimeout(120);
}

async function clickSvgAt(page, x, y) {
  await page.locator("svg").first().click({ position: { x, y } });
  await page.waitForTimeout(80);
}

test("mobile full feature flow", async ({ browser, page }) => {
  const runtime = attachRuntimeCollectors(page);

  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle");
  await page.locator(".mobile-pane-nav").waitFor({ state: "visible" });

  await gotoPane(page, "Components");
  await page.getByRole("button", { name: "+ Input", exact: true }).click();
  await page.getByRole("button", { name: "+ Input", exact: true }).click();
  await page.getByRole("button", { name: "AND Gate", exact: true }).click();
  await page.getByRole("button", { name: "Output", exact: true }).click();
  await waitForStatusIncludes(page, "Added output OUT1");

  await gotoPane(page, "Components");
  await page
    .getByRole("button", { name: "Wire Mode: OFF", exact: true })
    .click();
  await waitForStatusIncludes(page, "WIRE MODE");

  await gotoPane(page, "Canvas");

  await clickSvgAt(page, 170, 120);
  await clickSvgAt(page, 250, 280);

  await clickSvgAt(page, 170, 200);
  await clickSvgAt(page, 250, 300);

  await clickSvgAt(page, 340, 290);
  await clickSvgAt(page, 500, 360);

  await waitForWirePaths(page, 3);

  await gotoPane(page, "Components");
  await page
    .getByRole("button", { name: "Wire Mode: ON", exact: true })
    .click();
  await waitForStatusIncludes(page, "Ready");

  await gotoPane(page, "Canvas");
  await page
    .locator("svg")
    .first()
    .dblclick({ position: { x: 135, y: 120 } });

  await gotoPane(page, "Components");
  await page.getByRole("button", { name: "Simulate", exact: true }).click();
  await waitForStatusIncludes(page, "Simulation complete");

  await page.getByRole("button", { name: "Truth Table", exact: true }).click();
  await page
    .locator(".modal-card")
    .getByRole("heading", { name: "Truth Table" })
    .waitFor();
  await page.getByRole("button", { name: "Close" }).click();

  await page
    .getByRole("button", { name: "Timing Diagram", exact: true })
    .click();
  await page
    .locator(".modal-card")
    .getByRole("heading", { name: "Timing Diagram" })
    .waitFor();
  await page.getByRole("button", { name: "Close" }).click();

  await gotoPane(page, "Analysis");
  await page.getByRole("heading", { name: "Properties" }).waitFor();
  await page.getByRole("heading", { name: "Boolean Expression" }).waitFor();
  await page.getByRole("heading", { name: "Truth Table" }).waitFor();

  const propertiesSection = page.locator(".right-pane .panel-block").nth(0);
  const expressionSection = page.locator(".right-pane .panel-block").nth(1);

  await propertiesSection.getByRole("button", { name: "Collapse" }).click();
  await expect(propertiesSection.locator("pre")).toHaveCount(0);
  await propertiesSection.getByRole("button", { name: "Expand" }).click();
  await expect(propertiesSection.locator("pre")).toHaveCount(1);

  await expressionSection.getByRole("button", { name: "Collapse" }).click();
  await expect(expressionSection.locator("pre")).toHaveCount(0);
  await expressionSection.getByRole("button", { name: "Expand" }).click();
  await expect(expressionSection.locator("pre")).toHaveCount(1);

  const user1 = `e2e_mobile_${randomSuffix()}`;
  const user2 = `e2e_mobile_${randomSuffix()}`;
  const password = "password123";
  const circuitName = `e2e_mobile_ci_${randomSuffix()}`;
  const customGateName = `e2e_mobile_gate_${randomSuffix()}`;

  let circuitShareLink = "";
  let customGateShareLink = "";

  await gotoPane(page, "Components");
  await page.locator("#authUsername").fill(user1);
  await page.locator("#authPassword").fill(password);
  await page.getByRole("button", { name: "Register", exact: true }).click();
  await waitForCurrentUser(page, user1);

  await page.locator("#circuitName").fill(circuitName);
  await page.getByRole("button", { name: "Save To API", exact: true }).click();

  await page.getByRole("button", { name: "Refresh List", exact: true }).click();
  await page.locator("#savedCircuitSelect").selectOption({
    value: circuitName,
  });
  await page
    .getByRole("button", { name: "Load From API", exact: true })
    .click();

  await page
    .getByRole("button", {
      name: "Share Selected (Read-only)",
      exact: true,
    })
    .click();
  circuitShareLink = await waitForInputContains(page, "#shareLink", "?share=");
  expect(circuitShareLink).toContain("?share=");

  await page.locator("#customGateName").fill(customGateName);
  await page
    .getByRole("button", { name: "Create Custom Gate", exact: true })
    .click();

  const customGateButton = page.getByRole("button", {
    name: new RegExp(`${customGateName.toUpperCase()} \\(\\d+ in\\)`),
  });
  await customGateButton.waitFor();

  await page.getByRole("button", { name: `Share ${customGateName}` }).click();
  customGateShareLink = await waitForInputContains(
    page,
    "#sharedCustomGateLink",
    "gateShare=",
  );
  expect(customGateShareLink).toContain("gateShare=");

  await page.getByRole("button", { name: "Logout", exact: true }).click();
  await waitForCurrentUser(page, "guest");

  await page.locator("#authUsername").fill(user2);
  await page.locator("#authPassword").fill(password);
  await page.getByRole("button", { name: "Register", exact: true }).click();
  await waitForCurrentUser(page, user2);

  await page.locator("#importCustomGateShareId").fill(customGateShareLink);
  await page
    .getByRole("button", { name: "Import Shared Gate", exact: true })
    .click();

  await customGateButton.click();
  await waitForStatusIncludes(page, "Added gate");

  await page.getByRole("button", { name: "+ Input", exact: true }).click();
  await page
    .getByRole("button", { name: "Undo (Ctrl/Cmd+Z)", exact: true })
    .click();
  await waitForStatusIncludes(page, "Undo applied");
  await page
    .getByRole("button", { name: "Redo (Ctrl/Cmd+Y)", exact: true })
    .click();
  await waitForStatusIncludes(page, "Redo applied");

  const publicContext = await browser.newContext();
  const publicPage = await publicContext.newPage();
  const publicRuntime = attachRuntimeCollectors(publicPage);

  await publicPage.goto(circuitShareLink, { waitUntil: "domcontentloaded" });
  await publicPage.waitForLoadState("networkidle");
  await publicPage.locator(".mobile-pane-nav").waitFor({ state: "visible" });
  await waitForWirePaths(publicPage, 3);

  await gotoPane(publicPage, "Components");
  await expect(publicPage.locator("text=Current User:").first()).toContainText(
    "Guest",
  );
  await expect(
    publicPage.getByRole("button", { name: "Save To API", exact: true }),
  ).toBeDisabled();

  await assertNoRuntimeErrors(publicRuntime);
  await publicContext.close();

  await assertNoRuntimeErrors(runtime);
});
