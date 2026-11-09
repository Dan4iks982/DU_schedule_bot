const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, 'data');
if (!fs.existsSync(DATA_DIR)) {
  fs.mkdirSync(DATA_DIR, { recursive: true });
}

async function scrapeProgram(progCode = 'D01B9', semNum = '3') {
  const chromePath = process.env.PUPPETEER_EXECUTABLE_PATH || 
    (process.platform === 'win32' 
      ? 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe' 
      : '/usr/bin/chromium');

  const browser = await puppeteer.launch({
    executablePath: chromePath,
    headless: "new",
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
  });

  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1400, height: 1000 });

    await page.goto('https://luis.lu.lv/pls/du/pub_nod.main?l=1&p_au=D&p_mg=FO0064#skatit', {
      waitUntil: 'networkidle2',
      timeout: 30000
    });

    // 1. Program
    await page.type('#p_prg_input', progCode);
    await new Promise(r => setTimeout(r, 1200));
    const prgClicked = await page.evaluate((code) => {
      const picker = document.querySelector('#p_prg_input').closest('.multi-picker');
      for (const item of picker.querySelectorAll('li')) {
        if (item.innerText.includes(code)) {
          (item.querySelector('.multi-elem-base-value') || item).click();
          return true;
        }
      }
      return false;
    }, progCode);

    if (!prgClicked) {
      throw new Error(`Failed to find program: ${progCode}`);
    }

    await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 25000 });

    // 2. Semester
    await page.click('#p_sem_input');
    await new Promise(r => setTimeout(r, 1200));

    let mappedSem = semNum.toString();
    const autumnMap = { '2': '3', '4': '5', '6': '7', '8': '7' };
    if (autumnMap[mappedSem]) {
      mappedSem = autumnMap[mappedSem];
    }

    const semSelected = await page.evaluate((target) => {
      const picker = document.querySelector('#p_sem_input').closest('.multi-picker');
      if (!picker) return null;
      const items = Array.from(picker.querySelectorAll('li'));
      const matched = items.find(li => li.innerText.trim().startsWith(`${target}-`) || li.innerText.trim().startsWith(`${target}.`)) ||
                      items.find(li => li.innerText.includes(target));
      if (matched) {
        (matched.querySelector('.multi-elem-base-value') || matched).click();
        return matched.innerText.trim();
      }
      return null;
    }, mappedSem);

    if (semSelected) {
      await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 25000 });
    }

    // 3. Click Skatīt
    await Promise.all([
      page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 25000 }),
      page.evaluate(() => {
        const btns = Array.from(document.querySelectorAll('input[type="submit"]'));
        const btn = btns.find(b => b.value.includes('Skatīt'));
        if (btn) btn.click();
      })
    ]);

    await new Promise(r => setTimeout(r, 2000));

    // 4. Extract FullCalendar client events
    const clientEvents = await page.evaluate(() => {
      const cal = $('[id*="calendar"], .fc').first();
      if (cal.length && typeof cal.fullCalendar === 'function') {
        const evs = cal.fullCalendar('clientEvents');
        return evs.map(e => ({
          id: e.id,
          title: e.title,
          start: e.start ? e.start.toString() : null,
          end: e.end ? e.end.toString() : null,
          allDay: e.allDay,
          className: e.className,
          raw: Object.keys(e).reduce((acc, k) => {
            if (typeof e[k] !== 'function' && typeof e[k] !== 'object') acc[k] = e[k];
            return acc;
          }, {})
        }));
      }
      return [];
    });

    await browser.close();

    const outFileSem = path.join(DATA_DIR, `events_${progCode}_sem${semNum}.json`);
    fs.writeFileSync(outFileSem, JSON.stringify(clientEvents, null, 2), 'utf-8');

    if (typeof mappedSem !== 'undefined' && mappedSem !== semNum.toString()) {
      fs.writeFileSync(path.join(DATA_DIR, `events_${progCode}_sem${mappedSem}.json`), JSON.stringify(clientEvents, null, 2), 'utf-8');
    }

    const outFileMain = path.join(DATA_DIR, `events_${progCode}.json`);
    fs.writeFileSync(outFileMain, JSON.stringify(clientEvents, null, 2), 'utf-8');

    return { success: true, count: clientEvents.length };
  } catch (err) {
    if (browser) await browser.close().catch(() => {});
    return { success: false, error: err.message };
  }
}

(async () => {
  const targetCode = process.argv[2] || 'D01B9';
  const targetSem = process.argv[3] || '3';
  console.log(`Starting live scrape from LUIS for ${targetCode} semester ${targetSem}...`);
  const result = await scrapeProgram(targetCode, targetSem);
  
  if (result.success) {
    const syncInfo = {
      last_sync: new Date().toISOString(),
      program: targetCode,
      semester: targetSem,
      event_count: result.count
    };
    fs.writeFileSync(path.join(DATA_DIR, 'last_sync.json'), JSON.stringify(syncInfo, null, 2), 'utf-8');
  }
  
  console.log(JSON.stringify(result));
})();
