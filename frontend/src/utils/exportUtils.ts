/**
 * Export utilities for client-side file generation and download
 */
import JSZip from 'jszip';
import { saveAs } from 'file-saver';

export interface ExportFile {
  name: string;
  content: string;
}

export interface ExportFolder {
  name: string;
  files: ExportFile[];
}

/**
 * Sanitize a string for use as a filename/folder name
 */
export function sanitizeFilename(name: string): string {
  return name
    .replace(/[<>:"/\\|?*]/g, '_')  // Remove invalid characters
    .replace(/\s+/g, '_')            // Replace spaces with underscores
    .replace(/_+/g, '_')             // Collapse multiple underscores
    .substring(0, 100);              // Limit length
}

/**
 * Create and download a ZIP file containing multiple folders
 */
export async function downloadZip(
  folders: ExportFolder[],
  zipFilename: string,
  onProgress?: (current: number, total: number) => void
): Promise<void> {
  const zip = new JSZip();

  for (let i = 0; i < folders.length; i++) {
    const folder = folders[i];
    const zipFolder = zip.folder(folder.name);

    if (zipFolder) {
      for (const file of folder.files) {
        zipFolder.file(file.name, file.content);
      }
    }

    onProgress?.(i + 1, folders.length);
  }

  const blob = await zip.generateAsync({
    type: 'blob',
    compression: 'DEFLATE',
    compressionOptions: { level: 6 }
  });

  saveAs(blob, zipFilename);
}

/**
 * Download a single file
 */
export function downloadFile(content: string, filename: string, mimeType: string = 'text/plain'): void {
  const blob = new Blob([content], { type: mimeType });
  saveAs(blob, filename);
}
