const puppeteer = require('puppeteer-core');

(async () => {
  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/chromium',
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  const page = await browser.newPage();
  page.on('request', req => {
    if (req.resourceType() === 'xhr' || req.resourceType() === 'fetch') {
      console.log('AJAX REQ:', req.method(), req.url(), req.postData());
    }
  });

  await page.goto('https://luis.lu.lv/pls/du/pub_nod.main?l=1&p_au=D&p_mg=FO0064#skatit', {waitUntil: 'networkidle2'});
  await page.type('#p_prg_input', 'D12');
  await new Promise(r => setTimeout(r, 2000));

  const items = await page.evaluate(() => {
    const picker = document.querySelector('#p_prg_input').closest('.multi-picker');
    return picker ? Array.from(picker.querySelectorAll('li')).map(li => li.innerText.trim()) : [];
  });
  console.log('Items for D12:', JSON.stringify(items));
  await browser.close();
})();
