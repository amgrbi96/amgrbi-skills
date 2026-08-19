---
title: Security and Archival
description: qpdf encryption, repair and linearization; PDF/A conversion and validation with ghostscript and verapdf; tagged accessible PDFs with Puppeteer; PKCS#7 digital signing with @signpdf
tags: [qpdf, encryption, repair, linearize, PDF/A, verapdf, ghostscript, accessibility, signatures]
---

## qpdf — Encrypt, Repair, Linearize

```bash
# AES-256 encryption
qpdf --encrypt user-pass owner-pass 256 -- input.pdf secured.pdf

# Remove password protection (requires the current password)
qpdf --password=SECRET --decrypt input.pdf decrypted.pdf

# Fix a "Premature EOF" / corrupted structure in place
qpdf input.pdf --replace-input

# Fast web view — browsers stream page-by-page before the full download
qpdf --linearize input.pdf linearized.pdf

# Decompress to inspect raw objects (forensics)
qpdf --qdf --object-streams=disable input.pdf inspect.pdf
```

## PDF/A Compliance

PDF/A is an ISO standard (ISO 19005) for long-term archival: no JavaScript, no external font references, no encryption.

```bash
# Convert with ghostscript
gs -dPDFA=2 -dBATCH -dNOPAUSE -sDEVICE=pdfwrite \
  -sColorConversionStrategy=UseDeviceIndependentColor \
  -sOutputFile=output-pdfa.pdf input.pdf

# Validate — verapdf is the reference validator
verapdf --flavour 2b input.pdf
verapdf --format json input.pdf   # compliance status + violations
```

| Level   | Requirement                                      |
| ------- | ------------------------------------------------ |
| PDF/A-1 | Based on PDF 1.4, no transparency                |
| PDF/A-2 | Based on PDF 1.7, allows JPEG2000, layers        |
| PDF/A-3 | Same as 2, plus allows embedded file attachments |

Use PDF/A-2b for most archival use cases; the "b" means basic conformance (visual appearance only).

## Tagged PDFs for Accessibility

Tagged PDFs carry a structure tree that screen readers navigate. Generate them at creation time with Puppeteer — `tagged: true` maps HTML semantics to PDF structure tags:

```ts
const pdf = await page.pdf({
  format: 'A4',
  tagged: true,        // default in current Puppeteer
  printBackground: true,
});
```

Ensure the source HTML uses semantic markup (`<h1>`, `<table>`, `<figure>` with alt text) and set `<html lang="en">` for pronunciation. Validate against PDF/UA with `verapdf --flavour ua1 input.pdf`.

## Digital Signatures

### Signing with node-signpdf

```ts
import { plainAddPlaceholder } from '@signpdf/placeholder-plain';
import { P12Signer } from '@signpdf/signer-p12';
import signpdf from '@signpdf/signpdf';

async function signDocument(
  pdfBuffer: Buffer,
  p12Buffer: Buffer,
  passphrase: string,
) {
  const pdfWithPlaceholder = plainAddPlaceholder({
    pdfBuffer,
    reason: 'Document approval',
    contactInfo: 'signer@example.com',
    name: 'Authorized Signer',
    location: 'New York, US',
  });

  const signer = new P12Signer(p12Buffer, { passphrase });
  return await signpdf.sign(pdfWithPlaceholder, signer);
}
```

### Signature Verification

```ts
import { extractSignature } from '@signpdf/utils';
import * as forge from 'node-forge';

function verifySignature(signedPdfBuffer: Buffer) {
  const { signature, signedData } = extractSignature(signedPdfBuffer);

  const p7 = forge.pkcs7.messageFromAsn1(
    forge.asn1.fromDer(forge.util.createBuffer(signature)),
  );

  const cert = p7.certificates[0];
  return {
    signer: cert.subject.getField('CN')?.value,
    validFrom: cert.validity.notBefore,
    validTo: cert.validity.notAfter,
    isExpired: new Date() > cert.validity.notAfter,
  };
}
```

## Tool Selection

| Task                    | Tool                | Notes                                   |
| ----------------------- | ------------------- | --------------------------------------- |
| Encrypt / decrypt       | qpdf                | AES-256: `--encrypt user owner 256 --`  |
| Repair / linearize      | qpdf                | `--replace-input`, `--linearize`        |
| PDF/A conversion        | ghostscript         | `-dPDFA=2`                              |
| PDF/A + PDF/UA validate | verapdf             | `--flavour 2b` / `--flavour ua1`        |
| Tagged (accessible) PDF | Puppeteer           | `tagged: true` + semantic HTML          |
| Sign                    | @signpdf/\*         | PKCS#7 with P12 certificates            |
| Verify signature        | @signpdf/utils      | `extractSignature` + node-forge         |
