import { expect, test } from "@playwright/test";

test.describe.configure({ mode: "serial" });

function randomSuffix() {
  return Math.random().toString(36).slice(2, 10);
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

async function waitForStatusIncludes(page, fragment, timeout = 15_000) {
  const status = page.locator(".status-bar");
  await status.waitFor({ state: "visible", timeout });

  const started = Date.now();
  while (Date.now() - started < timeout) {
    const value = await status.innerText();
    if (value.includes(fragment)) {
      return value;
    }
    await page.waitForTimeout(120);
  }

  throw new Error(
    `Timed out waiting for status containing '${fragment}'. Last status: ${await status.innerText()}`,
  );
}

async function waitForStatusOneOf(page, fragments, timeout = 15_000) {
  const status = page.locator(".status-bar");
  await status.waitFor({ state: "visible", timeout });

  const started = Date.now();
  while (Date.now() - started < timeout) {
    const value = await status.innerText();
    if (fragments.some((fragment) => value.includes(fragment))) {
      return value;
    }
    await page.waitForTimeout(120);
  }

  throw new Error(
    `Timed out waiting for one of [${fragments.join(", ")}]. Last status: ${await status.innerText()}`,
  );
}

async function waitForCurrentUser(page, expectedUser, timeout = 15_000) {
  const label = page.locator("text=Current User:").first();
  await label.waitFor({ state: "visible", timeout });

  const expected = expectedUser.toLowerCase();
  const started = Date.now();
  while (Date.now() - started < timeout) {
    const value = (await label.innerText()).toLowerCase();
    if (value.includes(`current user: ${expected}`)) {
      return value;
    }
    await page.waitForTimeout(120);
  }

  throw new Error(
    `Timed out waiting for user '${expectedUser}'. Last label: ${await label.innerText()}`,
  );
}

async function waitForInputContains(
  page,
  selector,
  fragment,
  timeout = 15_000,
) {
  const input = page.locator(selector);
  await input.waitFor({ state: "visible", timeout });

  const started = Date.now();
  while (Date.now() - started < timeout) {
    const value = await input.inputValue();
    if (value.includes(fragment)) {
      return value;
    }
    await page.waitForTimeout(120);
  }

  throw new Error(
    `Timed out waiting for ${selector} to contain '${fragment}'. Last value: ${await input.inputValue()}`,
  );
}

async function waitForWirePaths(page, minimumCount, timeout = 15_000) {
  const started = Date.now();
  while (Date.now() - started < timeout) {
    const count = await page.locator("svg path").count();
    if (count >= minimumCount) {
      return count;
    }
    await page.waitForTimeout(120);
  }

  throw new Error(
    `Timed out waiting for at least ${minimumCount} wires. Last wire count: ${await page.locator("svg path").count()}`,
  );
}

async function clickSvgAt(page, x, y) {
  await page.locator("svg").first().click({ position: { x, y } });
  await page.waitForTimeout(80);
}

async function openDesktopApp(page, url = "/") {
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle");
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"], {
    origin: new URL(page.url()).origin,
  });
  await expect(page.getByRole("heading", { name: "Components" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Properties" })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Boolean Expression" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Truth Table" }),
  ).toBeVisible();
}

async function clearCircuitAndAccept(page) {
  page.once("dialog", (dialog) => dialog.accept());
  await page
    .getByRole("button", { name: "Clear Circuit", exact: true })
    .click();
  await waitForStatusIncludes(page, "Circuit cleared");
}

async function addCanonicalAndCircuit(page) {
  await page.getByRole("button", { name: "+ Input", exact: true }).click();
  await page.getByRole("button", { name: "+ Input", exact: true }).click();
  await page.getByRole("button", { name: "AND Gate", exact: true }).click();
  await page.getByRole("button", { name: "Output", exact: true }).click();
  await waitForStatusIncludes(page, "Added output OUT1");
}

async function wireCanonicalAndCircuit(page) {
  await page
    .getByRole("button", { name: "Wire Mode: OFF", exact: true })
    .click();
  await waitForStatusIncludes(page, "WIRE MODE");

  // IN1 -> AND input 0
  await clickSvgAt(page, 170, 120);
  await clickSvgAt(page, 250, 280);

  // IN2 -> AND input 1
  await clickSvgAt(page, 170, 200);
  await clickSvgAt(page, 250, 300);

  // AND -> OUT1
  await clickSvgAt(page, 340, 290);
  await clickSvgAt(page, 500, 360);

  await waitForWirePaths(page, 3);

  await page
    .getByRole("button", { name: "Wire Mode: ON", exact: true })
    .click();
  await waitForStatusIncludes(page, "Ready");
}

async function buildCanonicalAndCircuit(page) {
  await addCanonicalAndCircuit(page);
  await wireCanonicalAndCircuit(page);
}

async function registerUser(page, username, password) {
  await page.locator("#authUsername").fill(username);
  await page.locator("#authPassword").fill(password);
  await page.getByRole("button", { name: "Register", exact: true }).click();
  await waitForCurrentUser(page, username);
}

async function loginUser(page, username, password) {
  await page.locator("#authUsername").fill(username);
  await page.locator("#authPassword").fill(password);
  await page.getByRole("button", { name: "Login", exact: true }).click();
  await waitForCurrentUser(page, username);
}

test("desktop core UI interactions and analysis flow", async ({ page }) => {
  const runtime = attachRuntimeCollectors(page);
  await openDesktopApp(page);

  const gateButtons = [
    "AND Gate",
    "OR Gate",
    "NOT Gate",
    "NAND Gate",
    "NOR Gate",
    "XOR Gate",
  ];
  for (const gateName of gateButtons) {
    await page.getByRole("button", { name: gateName, exact: true }).click();
    await waitForStatusIncludes(page, "Added gate");
  }

  await clearCircuitAndAccept(page);
  await buildCanonicalAndCircuit(page);

  await page
    .locator("svg")
    .first()
    .dblclick({ position: { x: 135, y: 120 } });
  await page
    .locator("svg")
    .first()
    .dblclick({ position: { x: 135, y: 200 } });

  await page.getByRole("button", { name: "Simulate", exact: true }).click();
  await waitForStatusIncludes(page, "Simulation complete");

  await expect(page.locator(".panel-truth pre")).toContainText("1 | 1 | 1");

  await page.getByRole("button", { name: "Truth Table", exact: true }).click();
  await expect(
    page.locator(".modal-card").getByRole("heading", { name: "Truth Table" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Close", exact: true }).click();

  await page
    .getByRole("button", { name: "Timing Diagram", exact: true })
    .click();
  await expect(
    page
      .locator(".modal-card")
      .getByRole("heading", { name: "Timing Diagram" }),
  ).toBeVisible();
  await expect(page.locator(".truth-modal-pre")).toContainText("Step:");
  await page.getByRole("button", { name: "Close", exact: true }).click();

  await clickSvgAt(page, 260, 270);
  await expect(
    page.locator(".panel-block").first().locator("pre"),
  ).toContainText("Gate:");

  await page.keyboard.press("Delete");
  await waitForStatusIncludes(page, "deleted");

  await page
    .getByRole("button", { name: "Undo (Ctrl/Cmd+Z)", exact: true })
    .click();
  await waitForStatusIncludes(page, "Undo applied");

  await page.keyboard.press("Control+Y");
  await waitForStatusIncludes(page, "Redo applied");

  await page.keyboard.press("Control+Z");
  await waitForStatusIncludes(page, "Undo applied");

  await clearCircuitAndAccept(page);
  await page
    .getByRole("button", { name: "Undo (Ctrl/Cmd+Z)", exact: true })
    .click();
  await waitForStatusIncludes(page, "Undo applied");
  await waitForWirePaths(page, 3);

  await assertNoRuntimeErrors(runtime);
});

test("auth, persistence, and public read-only sharing", async ({
  browser,
  page,
}) => {
  const runtime = attachRuntimeCollectors(page);
  await openDesktopApp(page);
  await buildCanonicalAndCircuit(page);

  const username = `desktop_${randomSuffix()}`;
  const password = "password123";
  const circuitName = `desktop_ci_${randomSuffix()}`;

  await registerUser(page, username, password);

  await page.locator("#circuitName").fill(circuitName);
  await page.getByRole("button", { name: "Save To API", exact: true }).click();

  await page.getByRole("button", { name: "Refresh List", exact: true }).click();
  await expect(
    page.locator(`#savedCircuitSelect option[value='${circuitName}']`),
  ).toHaveCount(1);

  await page.locator("#savedCircuitSelect").selectOption(circuitName);
  await page
    .getByRole("button", { name: "Load From API", exact: true })
    .click();
  await waitForWirePaths(page, 3);

  await page
    .getByRole("button", {
      name: "Share Selected (Read-only)",
      exact: true,
    })
    .click();

  const shareLink = await waitForInputContains(page, "#shareLink", "?share=");

  await page
    .getByRole("button", { name: "Copy Share Link", exact: true })
    .click();
  await waitForStatusOneOf(page, [
    "Share link copied",
    "Clipboard API unavailable",
    "Could not copy link",
  ]);

  await page.getByRole("button", { name: "Logout", exact: true }).click();
  await waitForCurrentUser(page, "guest");
  await loginUser(page, username, password);

  const publicContext = await browser.newContext({
    viewport: { width: 1600, height: 960 },
  });
  const publicPage = await publicContext.newPage();
  const publicRuntime = attachRuntimeCollectors(publicPage);

  await openDesktopApp(publicPage, shareLink);
  await waitForWirePaths(publicPage, 3);

  await expect(publicPage.locator("text=Current User:").first()).toContainText(
    "Guest",
  );
  await expect(
    publicPage.getByRole("button", { name: "Save To API", exact: true }),
  ).toBeDisabled();

  await publicPage
    .getByRole("button", { name: "Simulate", exact: true })
    .click();
  await waitForStatusIncludes(publicPage, "Simulation complete");

  await assertNoRuntimeErrors(publicRuntime);
  await publicContext.close();

  await assertNoRuntimeErrors(runtime);
});

test("custom gate create/share/import and auto-import via gateShare URL", async ({
  page,
}) => {
  const runtime = attachRuntimeCollectors(page);
  await openDesktopApp(page);
  await buildCanonicalAndCircuit(page);

  const owner = `desktop_${randomSuffix()}`;
  const importer = `desktop_${randomSuffix()}`;
  const autoImporter = `desktop_${randomSuffix()}`;
  const password = "password123";
  const customGateName = `desktop_gate_${randomSuffix()}`;

  await registerUser(page, owner, password);

  await page.locator("#customGateName").fill(customGateName);
  await page
    .getByRole("button", { name: "Create Custom Gate", exact: true })
    .click();

  const customGateButton = page.getByRole("button", {
    name: new RegExp(`${customGateName.toUpperCase()} \\(\\d+ in\\)`),
  });
  await customGateButton.waitFor();

  await page.getByRole("button", { name: `Share ${customGateName}` }).click();
  const sharedGateLink = await waitForInputContains(
    page,
    "#sharedCustomGateLink",
    "gateShare=",
  );

  await page
    .getByRole("button", {
      name: "Copy Shared Custom Gate Link",
      exact: true,
    })
    .click();
  await waitForStatusOneOf(page, [
    "Shared custom gate link copied",
    "Clipboard API unavailable",
  ]);

  await page.getByRole("button", { name: "Logout", exact: true }).click();
  await waitForCurrentUser(page, "guest");

  await registerUser(page, importer, password);

  await page.locator("#importCustomGateShareId").fill(sharedGateLink);
  await page
    .getByRole("button", { name: "Import Shared Gate", exact: true })
    .click();

  await customGateButton.waitFor();
  await customGateButton.click();
  await waitForStatusIncludes(page, "Added gate");

  await page
    .getByRole("button", { name: "Undo (Ctrl/Cmd+Z)", exact: true })
    .click();
  await waitForStatusIncludes(page, "Undo applied");

  await page.keyboard.press("Control+Y");
  await waitForStatusIncludes(page, "Redo applied");

  await page.getByRole("button", { name: "Logout", exact: true }).click();
  await waitForCurrentUser(page, "guest");

  await registerUser(page, autoImporter, password);

  await openDesktopApp(page, sharedGateLink);
  await customGateButton.waitFor();

  await assertNoRuntimeErrors(runtime);
});
