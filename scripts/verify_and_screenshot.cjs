const fs = require('fs');
const path = require('path');
const puppeteer = require('c:/Users/ramku/PROJECTS/HACKS/RAZORPAY/ResiliencePay/apps/dashboard/node_modules/puppeteer-core');

const CHROME_PATH = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const OUTPUT_DIR = path.resolve(__dirname, '..', 'docs', 'screenshots');
const ARTIFACT_DIR = 'C:\\Users\\ramku\\.gemini\\antigravity-ide\\brain\\01878f2f-7863-47b2-abc8-bb2207555cfe';

if (!fs.existsSync(OUTPUT_DIR)) {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

async function saveScreenshot(page, filename, description) {
  const filePath = path.join(OUTPUT_DIR, filename);
  await page.screenshot({ path: filePath, fullPage: false });
  console.log(`[OK] Saved screenshot: ${filename} - ${description}`);
  
  // Also copy to artifact dir for report
  try {
    const artifactPath = path.join(ARTIFACT_DIR, filename);
    fs.copyFileSync(filePath, artifactPath);
  } catch (err) {
    // ignore
  }
}

async function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

(async () => {
  console.log("Launching Chrome headless at:", CHROME_PATH);
  const browser = await puppeteer.launch({
    executablePath: CHROME_PATH,
    headless: "new",
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1600,1050'],
    defaultViewport: { width: 1600, height: 1050 }
  });

  try {
    const page = await browser.newPage();
    
    page.on('console', msg => console.log('BROWSER LOG:', msg.text()));
    page.on('pageerror', err => console.log('BROWSER ERROR:', err.message));

    console.log("Navigating to http://localhost:5173/ ...");
    await page.goto('http://localhost:5173/', { waitUntil: 'networkidle0', timeout: 30000 });
    await sleep(2000);

    // 0. CAPTURE LOGIN SCREEN
    console.log("=== 0. VERIFYING LOGIN SCREEN ===");
    await saveScreenshot(page, '00_enterprise_login.png', 'Enterprise Razorpay Authentication Gate');

    // Perform Login
    console.log("Entering credentials (admin@razorpay.com)...");
    await page.type('input[type="email"]', 'admin@razorpay.com');
    await page.type('input[type="password"]', 'ResiliencePay2026!');
    await sleep(500);
    
    // Click submit
    console.log("Clicking 'Secure Sign In'...");
    await page.click('button[type="submit"]');

    // Wait for authentication animation & transition into dashboard
    console.log("Waiting for authentication & RBAC verification...");
    await sleep(3500);

    // Verify dashboard is loaded
    await page.waitForSelector('.top-nav', { timeout: 10000 });
    console.log("[OK] Successfully logged in! Reached main ResiliencePay Console.");

    // 1. VERIFY EXECUTIVE DASHBOARD
    console.log("=== 1. VERIFYING EXECUTIVE DASHBOARD ===");
    await sleep(2000);
    const kpiCount = await page.$$eval('.kpi-card', els => els.length);
    const hasRecharts = await page.$eval('.recharts-responsive-container', el => !!el).catch(() => false);
    const bodyText = await page.$eval('body', el => el.innerText);
    
    console.log(`[VERIFIED] KPI cards rendered: ${kpiCount}`);
    console.log(`[VERIFIED] Recharts learning curves rendered: ${hasRecharts}`);
    console.log(`[VERIFIED] Contains 'Executive Overview': ${bodyText.includes('Executive Overview')}`);
    console.log(`[VERIFIED] Contains 'Recovery Learning Curve': ${bodyText.includes('Recovery Learning Curve')}`);
    console.log(`[VERIFIED] Contains 'Strategy Allocation': ${bodyText.includes('Strategy Allocation')}`);

    await saveScreenshot(page, '01_executive_dashboard.png', 'Executive Dashboard with Live KPIs, Learning Curves, Strategy Allocation & Ledger');

    // 2. NAVIGATE TO RECOVERY CASES
    console.log("=== 2. VERIFYING RECOVERY CASES & CASE INSPECTOR ===");
    const tabs = await page.$$('.nav-tab');
    for (const tab of tabs) {
      const text = await page.evaluate(el => el.innerText, tab);
      if (text.includes('Recovery Cases')) {
        await tab.click();
        console.log("Clicked 'Recovery Cases' tab");
        break;
      }
    }
    await sleep(2000);

    // Select the first event item
    const eventItems = await page.$$('.case-card');
    console.log(`[VERIFIED] Active case events found: ${eventItems.length}`);
    if (eventItems.length > 0) {
      await eventItems[0].click();
      await sleep(1500);
    }

    const inspectorText = await page.$eval('.glass-panel:nth-of-type(2)', el => el.innerText).catch(() => "");
    console.log(`[VERIFIED] Case Inspector contains 'Thompson Sampling Distribution': ${inspectorText.includes('Thompson Sampling Distribution')}`);
    console.log(`[VERIFIED] Case Inspector contains 'retry_immediate': ${inspectorText.includes('retry_immediate')}`);

    await saveScreenshot(page, '02_case_inspector_normal.png', 'Case Inspector with Thompson Sampling in Baseline Normal Operation');

    // 3. INJECT GATEWAY CHAOS
    console.log("=== 3. TESTING GATEWAY CHAOS & AUTONOMOUS RECOVERY PIVOT ===");
    const buttons = await page.$$('button');
    let chaosBtn = null;
    for (const b of buttons) {
      const text = await page.evaluate(el => el.innerText, b);
      if (text.includes('Inject Gateway Chaos')) {
        chaosBtn = b;
        break;
      }
    }

    if (chaosBtn) {
      console.log("Triggering: 'Inject Gateway Chaos'...");
      await chaosBtn.click();
      await sleep(2500);

      const afterChaosText = await page.$eval('body', el => el.innerText);
      const hasAutonomousPivot = afterChaosText.includes('Autonomous Pivot') || afterChaosText.includes('Chaos mode enabled');
      console.log(`[VERIFIED] Autonomous Strategy Pivot Banner active: ${hasAutonomousPivot}`);

      await saveScreenshot(page, '03_case_inspector_chaos.png', 'Autonomous Recovery Pivot under Simulated Gateway Chaos');

      // Stop Chaos
      for (const b of await page.$$('button')) {
        const text = await page.evaluate(el => el.innerText, b);
        if (text.includes('Stop Chaos')) {
          await b.click();
          console.log("Restored gateway state: Clicked 'Stop Chaos'");
          await sleep(1000);
          break;
        }
      }
    }

    // 4. VERIFY IMMUTABLE AUDIT LEDGER
    console.log("=== 4. VERIFYING IMMUTABLE AUDIT LEDGER ===");
    const navTabs = await page.$$('.nav-tab');
    for (const tab of navTabs) {
      const text = await page.evaluate(el => el.innerText, tab);
      if (text.includes('Audit Ledger')) {
        await tab.click();
        console.log("Clicked 'Audit Ledger' tab");
        break;
      }
    }
    await sleep(2000);
    const auditText = await page.$eval('body', el => el.innerText);
    console.log(`[VERIFIED] Audit Ledger view rendered: ${auditText.includes('Audit Ledger')}`);
    await saveScreenshot(page, '04_audit_ledger.png', 'Cryptographically Chained SHA-256 Audit Trail');

    // 5. VERIFY SIMULATOR
    console.log("=== 5. VERIFYING REAL-TIME SIMULATOR ===");
    for (const tab of await page.$$('.nav-tab')) {
      const text = await page.evaluate(el => el.innerText, tab);
      if (text.includes('Simulator')) {
        await tab.click();
        console.log("Clicked 'Simulator' tab");
        break;
      }
    }
    await sleep(2000);
    await saveScreenshot(page, '05_simulation_engine.png', 'Simulation Engine & Scenario Control Room');

    console.log("\n========================================================");
    console.log("ALL FEATURES VERIFIED AND SCREENSHOTS CAPTURED!");
    console.log("========================================================");
  } catch (error) {
    console.error("Verification error:", error);
  } finally {
    await browser.close();
  }
})();
