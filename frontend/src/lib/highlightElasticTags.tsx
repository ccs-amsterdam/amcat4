import { ReactElement } from "react";

/***
 *
 * Replace <em> tags in the input string by <highlight> jsx tags
 *
 */
export function highlightElasticTags(text: string): ReactElement<any> {
  // if </em> is immediately followed by <em>, remove them to the sequence is highlighted
  text = text.replaceAll("</em> <em>", " ");

  const regex = new RegExp(/<em>(.*?)<\/em>/); // Match text inside two square brackets
  return (
    <>
      {String(text)
        .split(regex)
        .reduce((prev: (string | ReactElement<any>)[], tagged: string, i) => {
          const cleanTagged = tagged.replaceAll("<em>", "").replaceAll("</em>", "");
          if (i % 2 === 0) {
            prev.push(cleanTagged);
          } else {
            prev.push(
              <span className="rounded bg-secondary px-[3px] text-secondary-foreground  " key={i}>
                {cleanTagged}
              </span>,
            );
          }
          return prev;
        }, [])}
    </>
  );
}

/**
 * Remove all <em> / </em> tags from a string
 *
 * @param text The input text
 * @returns the text without </?em> tags
 */
export function removeElasticTags(text: string): string {
  return String(text).replaceAll("<em>", "").replaceAll("</em>", "");
}
