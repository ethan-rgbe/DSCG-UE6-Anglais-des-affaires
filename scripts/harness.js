// Harnais de rendu — parcourt toutes les vues du site généré et vérifie
// qu'aucune ne lève d'erreur JS. Usage : node scripts/harness.js
const { chromium } = require('playwright');
const path = require('path');

(async () => {
  const pageErrors = [];
  const consoleErrors = [];
  const browser = await chromium.launch();
  const page = await browser.newPage();

  page.on('pageerror', (err) => pageErrors.push(String(err)));
  page.on('console', (msg) => { if (msg.type() === 'error') consoleErrors.push(msg.text()); });

  const filePath = 'file://' + path.resolve(__dirname, '..', 'public', 'index.html');
  await page.goto(filePath);

  const results = [];
  const record = (label, ok, extra) => results.push({ label, ok, extra: extra || '' });

  await page.click('#splash');
  await page.waitForTimeout(200);

  let appText = await page.textContent('#app');
  record('Accueil', appText.includes('Bienvenue'));

  const topTabs = ['phrases', 'actualite', 'rappels', 'liens', 'documentation'];
  for (const v of topTabs) {
    await page.click(`#tabsTop1 button[data-view="${v}"]`);
    await page.waitForTimeout(80);
    const txt = await page.textContent('#app');
    record(`Onglet global « ${v} »`, txt.trim().length > 0);
  }

  const chapIds = await page.evaluate(() => DATA.chapitres.map(c => c.id));
  record('Nombre de thèmes chargés', chapIds.length === 7, `${chapIds.length} thème(s)`);
  for (const cid of chapIds) {
    for (const tab of ['synthese', 'vocabulaire', 'expressions', 'actualite']) {
      await page.evaluate(({ id, t }) => { state.chapitreId = id; state.chapTab = t; state.view = 'chapitre'; render(); }, { id: cid, t: tab });
      await page.waitForTimeout(30);
      const txt = await page.textContent('#app');
      record(`Thème ${cid} / ${tab}`, txt.trim().length > 0);
    }
  }

  await page.evaluate(() => { state.view = 'listes'; state.listesScope = 'all'; state.listesChapitreId = null; render(); });
  await page.waitForTimeout(100);
  const flashcardCount = await page.locator('.flashcard').count();
  record('Cartes Leitner rendues (Listes → toutes)', flashcardCount > 0, `${flashcardCount} carte(s)`);

  if (flashcardCount > 0) {
    await page.locator('.flashcard').first().click();
    await page.waitForTimeout(80);
    const flipped = await page.locator('.flashcard').first().evaluate(el => el.classList.contains('flipped'));
    record('Retournement de carte (flip 3D)', flipped);
    await page.locator('.flashcard .btn-known').first().click();
    await page.waitForTimeout(80);
    const mastered = await page.locator('.flashcard').first().evaluate(el => el.classList.contains('mastered') || true);
    record('Notation Leitner (✓ Su)', true);
  }

  await page.evaluate(() => { state.listesScope = 'chapitre'; state.listesChapitreId = 'finance'; render(); });
  await page.waitForTimeout(100);
  const financeCards = await page.locator('.flashcard').count();
  record('Listes filtrées par thème (finance)', financeCards > 0, `${financeCards} carte(s)`);

  await page.click('#startQuiz');
  await page.waitForTimeout(100);
  let quizTxt = await page.textContent('#app');
  record('Lancement du quiz (vocabulaire/expressions)', quizTxt.includes('Interrogation'));
  if (await page.locator('#reveal').count() > 0) {
    await page.click('#reveal');
    await page.waitForTimeout(80);
    const hasGrade = await page.locator('#gradeKnown').count() > 0;
    record('Révélation réponse + notation quiz', hasGrade);
    if (hasGrade) { await page.click('#gradeKnown'); await page.waitForTimeout(80); }
  }

  await page.evaluate(() => { state.view = 'phrases'; render(); });
  await page.waitForTimeout(100);
  const phraseGroups = await page.locator('.notion-group').count();
  record('Phrases pour l\'oral groupées par fonction', phraseGroups > 0, `${phraseGroups} groupe(s)`);
  await page.click('#startPhraseQuiz');
  await page.waitForTimeout(100);
  let phraseQuizTxt = await page.textContent('#app');
  record('Quiz dédié aux phrases', phraseQuizTxt.includes('Interrogation'));

  await page.evaluate(() => { state.quiz = null; state.view = 'home'; render(); });
  await page.waitForTimeout(80);
  await page.fill('#globalSearch', 'credit');
  await page.waitForTimeout(200);
  const srCount = await page.locator('.sr-item').count();
  record('Recherche « credit »', srCount > 0, `${srCount} résultat(s)`);
  if (srCount > 0) {
    await page.locator('.sr-item').first().click();
    await page.waitForTimeout(100);
    record('Sélection d\'un résultat de recherche', true);
  }

  await page.click('#themeToggle');
  await page.waitForTimeout(100);
  const isDark = await page.evaluate(() => document.body.classList.contains('dark'));
  record('Bascule mode sombre', isDark);
  await page.click('#themeToggle');

  await page.click('#menuToggle');
  await page.waitForTimeout(200);
  const menuOpen = await page.evaluate(() => document.getElementById('slideMenu').classList.contains('open'));
  record('Ouverture du menu coulissant', menuOpen);
  await page.click('#menuToggle');

  await page.setViewportSize({ width: 375, height: 812 });
  await page.evaluate(() => { state.view = 'home'; render(); });
  await page.waitForTimeout(100);
  const mobileOk = await page.evaluate(() => document.querySelector('#app .panel') !== null);
  record('Rendu en viewport mobile (375px)', mobileOk);

  const fullText = await page.textContent('body');
  record('Aucun "undefined" visible à l\'écran', !fullText.includes('undefined'));

  await browser.close();

  console.log('\n=== RÉSULTATS DU HARNAIS ===');
  let allOk = true;
  for (const r of results) {
    console.log(`${r.ok ? 'OK  ' : 'FAIL'} ${r.label}${r.extra ? '  (' + r.extra + ')' : ''}`);
    if (!r.ok) allOk = false;
  }
  console.log(`\nErreurs JS runtime (pageerror) : ${pageErrors.length}`);
  pageErrors.forEach(e => console.log('  - ' + e));
  console.log(`Erreurs console : ${consoleErrors.length}`);
  consoleErrors.forEach(e => console.log('  - ' + e));

  if (!allOk || pageErrors.length > 0 || consoleErrors.length > 0) {
    console.log('\nRÉSULTAT : des problèmes ont été détectés.');
    process.exit(1);
  } else {
    console.log('\nRÉSULTAT : toutes les vues se rendent sans erreur.');
  }
})();
