const puppeteer = require('puppeteer-core');
const fs = require('fs');

(async () => {
  const browser = await puppeteer.launch({
    executablePath: process.platform === 'win32' 
      ? 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe' 
      : '/usr/bin/chromium',
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  try {
    const page = await browser.newPage();
    await page.goto('https://luis.lu.lv/pls/du/pub_nod.main?l=1&p_au=D&p_mg=FO0064#skatit', {waitUntil: 'networkidle2', timeout: 30000});

    await page.click('#p_fak_input');
    await new Promise(r => setTimeout(r, 1200));
    const faculties = await page.evaluate(() => {
      const picker = document.querySelector('#p_fak_input').closest('.multi-picker');
      return picker ? Array.from(picker.querySelectorAll('li')).map(li => li.innerText.trim()).filter(Boolean) : [];
    });
    console.log('FACULTIES:', JSON.stringify(faculties));

    const result = {};
    for (const fak of faculties) {
      console.log(`Processing faculty: ${fak}...`);
      await page.goto('https://luis.lu.lv/pls/du/pub_nod.main?l=1&p_au=D&p_mg=FO0064#skatit', {waitUntil: 'networkidle2', timeout: 30000});
      await page.click('#p_fak_input');
      await new Promise(r => setTimeout(r, 1200));
      await page.evaluate((targetFak) => {
        const picker = document.querySelector('#p_fak_input').closest('.multi-picker');
        const items = Array.from(picker.querySelectorAll('li'));
        const match = items.find(li => li.innerText.trim() === targetFak);
        if (match) {
          (match.querySelector('.multi-elem-base-value') || match).click();
        }
      }, fak);

      await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 25000 }).catch(() => {});
      await page.click('#p_prg_input');
      await new Promise(r => setTimeout(r, 1200));

      const programs = await page.evaluate(() => {
        const picker = document.querySelector('#p_prg_input').closest('.multi-picker');
        if (!picker) return [];
        return Array.from(picker.querySelectorAll('li')).map(li => li.innerText.trim()).filter(Boolean);
      });

      result[fak] = programs;
      console.log(`Found ${programs.length} programs for ${fak}`);
    }

    fs.writeFileSync('du_faculties_programs.json', JSON.stringify(result, null, 2), 'utf-8');
    console.log('SAVED to du_faculties_programs.json');
  } catch (err) {
    console.error('Error:', err);
  } finally {
    await browser.close();
  }
})();
