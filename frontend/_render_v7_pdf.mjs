import { chromium } from "playwright";
import path from "node:path";
import { pathToFileURL } from "node:url";

const root = path.resolve(process.cwd(), "..");
const htmlPath = path.join(root, "v7_specialist_report.html");
const pdfPath = path.join(root, "v7_specialist_report.pdf");

const browser = await chromium.launch();
const page = await browser.newPage();
await page.goto(pathToFileURL(htmlPath).href, { waitUntil: "networkidle" });
await page.pdf({
  path: pdfPath,
  format: "A4",
  printBackground: true,
  margin: { top: "16mm", bottom: "16mm", left: "14mm", right: "14mm" },
});
await browser.close();
console.log("Wrote", pdfPath);
