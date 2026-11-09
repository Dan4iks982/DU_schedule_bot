const puppeteer = require('puppeteer-core');

(async () => {
  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/chromium',
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  const page = await browser.newPage();
  await page.goto('https://luis.lu.lv/pls/du/pub_nod.main?l=1&p_au=D&p_mg=FO0064#skatit', {waitUntil: 'networkidle2'});

  const res = await page.evaluate(() => {
    // Check if there is a data attribute or global array with all options
    const input = document.getElementById('p_prg_input');
    // In LUIS multi-picker:
    return {
      name: input ? input.name : null,
      dataset: input ? Object.keys(input.dataset) : [],
    };
  });
  console.log(JSON.stringify(res));

  // Let's test typing letters a-z or digits to see all options
  // Or check the HTML source of the page for program list
  const html = await page.content();
  const matches = html.match(/D[0-9]{2}[A-Z0-9]{2}/g);
  console.log('Program codes in HTML:', [...new Set(matches || [])]);

  await browser.close();
})();
