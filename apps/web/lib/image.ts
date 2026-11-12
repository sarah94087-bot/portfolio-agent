// A screenshot of a job posting, made ready to send (ADR-0022). The pure parts are tested; only
// `prepareImage` touches the browser. The server checks the type again, by the file's first
// bytes, and nothing of the picture is kept there.

export const ACCEPT = "image/png,image/jpeg,image/webp";
export const TYPES = ["image/png", "image/jpeg", "image/webp"];
export const MAX_INPUT_BYTES = 15_000_000; // what the browser is asked to open
export const MAX_SENT_BYTES = 1_500_000; // under Vercel's 4.5 MB body, with room for the base64
export const MAX_WIDTH = 1600;
export const MAX_HEIGHT = 4000; // a whole page is tall; the model reads it in tiles

export type ImageError = "type" | "size" | "decode";

export class ImageProblem extends Error {
  code: ImageError;
  constructor(code: ImageError) {
    super(code);
    this.code = code;
  }
}

/** The size to draw at: inside the box, never larger than the original, same proportions. */
export function fitWithin(width: number, height: number, maxWidth = MAX_WIDTH, maxHeight = MAX_HEIGHT) {
  const scale = Math.min(1, maxWidth / width, maxHeight / height);
  return { width: Math.max(1, Math.round(width * scale)), height: Math.max(1, Math.round(height * scale)) };
}

/** What is wrong with a file before it is opened, if anything. */
export function checkFile(file: { type: string; size: number }): ImageError | null {
  if (!TYPES.includes(file.type)) return "type";
  return file.size > MAX_INPUT_BYTES ? "size" : null;
}

/** The first image among pasted or dropped items. */
export function firstImage(files: Iterable<File> | ArrayLike<File> | null | undefined): File | undefined {
  return files ? Array.from(files).find((f) => f.type.startsWith("image/")) : undefined;
}

/** Bytes of a data URL's payload, without decoding it. */
export function dataUrlBytes(url: string): number {
  const payload = url.slice(url.indexOf(",") + 1);
  const padding = payload.endsWith("==") ? 2 : payload.endsWith("=") ? 1 : 0;
  return Math.floor((payload.length * 3) / 4) - padding;
}

const read = (blob: Blob) =>
  new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });

/** Scales the picture down and compresses it until it fits, as a data URL. Screenshots of text
 * keep their edges at WebP 0.85; Safari cannot write WebP and gives PNG, which the loop then
 * shrinks by size instead. */
export async function prepareImage(file: File): Promise<string> {
  const problem = checkFile(file);
  if (problem) throw new ImageProblem(problem);
  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(file);
  } catch {
    throw new ImageProblem("decode");
  }
  try {
    let { width, height } = fitWithin(bitmap.width, bitmap.height);
    for (const quality of [0.85, 0.7, 0.55, 0.4]) {
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const context = canvas.getContext("2d");
      if (!context) throw new ImageProblem("decode");
      context.drawImage(bitmap, 0, 0, width, height);
      const blob = await new Promise<Blob | null>((done) => canvas.toBlob(done, "image/webp", quality));
      if (!blob) throw new ImageProblem("decode");
      if (blob.size <= MAX_SENT_BYTES) return await read(blob);
      ({ width, height } = fitWithin(width * 0.85, height * 0.85));
    }
    throw new ImageProblem("size");
  } finally {
    bitmap.close();
  }
}
