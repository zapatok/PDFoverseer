// Valor de cada palabra-átomo. Un número 0–999 en español es la SUMA de sus
// átomos (centena + decena/forma especial + unidad); la conjunción "y" se
// ignora. Las formas se guardan sin acento — el parser normaliza la entrada.
const WORD_VALUE = {
  cero: 0, uno: 1, un: 1, una: 1, dos: 2, tres: 3, cuatro: 4, cinco: 5,
  seis: 6, siete: 7, ocho: 8, nueve: 9,
  diez: 10, once: 11, doce: 12, trece: 13, catorce: 14, quince: 15,
  dieciseis: 16, diecisiete: 17, dieciocho: 18, diecinueve: 19,
  veinte: 20, veintiuno: 21, veintidos: 22, veintitres: 23, veinticuatro: 24,
  veinticinco: 25, veintiseis: 26, veintisiete: 27, veintiocho: 28, veintinueve: 29,
  treinta: 30, cuarenta: 40, cincuenta: 50, sesenta: 60,
  setenta: 70, ochenta: 80, noventa: 90,
  cien: 100, ciento: 100, doscientos: 200, trescientos: 300, cuatrocientos: 400,
  quinientos: 500, seiscientos: 600, setecientos: 700, ochocientos: 800,
  novecientos: 900,
};

/**
 * Convierte una transcripción de voz o de teclado en un entero 0–999, o null si
 * no es un número reconocible. Acepta dígitos ("23") y palabras en español
 * ("veintitrés", "ciento cinco", "cuarenta y uno").
 *
 * @param {string} text
 * @returns {number|null}
 */
export function parseSpanishNumber(text) {
  if (typeof text !== "string") return null;
  // minúsculas y sin acentos
  const norm = text
    .toLowerCase()
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .trim();
  if (norm === "") return null;

  // ¿dígitos? — el Web Speech API suele transcribir "veintitrés" como "23"
  const digitRun = norm.match(/\d+/);
  if (digitRun) {
    const n = parseInt(digitRun[0], 10);
    return n >= 0 && n <= 999 ? n : null;
  }

  // palabras: suma de átomos, ignorando "y"
  let total = 0;
  let matched = 0;
  for (const token of norm.split(/[\s-]+/)) {
    if (token === "" || token === "y") continue;
    const value = WORD_VALUE[token];
    if (value === undefined) continue;
    total += value;
    matched += 1;
  }
  if (matched === 0) return null;
  return total >= 0 && total <= 999 ? total : null;
}
