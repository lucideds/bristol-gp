# Pippin: Algorithm flowcharts

Last updated 28 October 2026.

This is Brief Task 1, Activity B. It shows five of the more complex things T Level Connect does as simple flowcharts for a non-technical audience. The detailed versions, with every rule and limit, are the pseudocode in [algorithm-designs.md](algorithm-designs.md).

For presenting or printing, use [algorithm-flowcharts.pdf](algorithm-flowcharts.pdf): a key page, then one chart per A4 page.

How to read them: start at the dark box at the top and follow the arrows. Orange diamonds are questions, so follow Yes or No. White boxes are things the website does. Green boxes are good endings, red boxes are where it stops and tells the visitor why, and grey dashed boxes are notes.

1. [Signing up and signing in](flowcharts/1-register-login.png)
2. [Asking the chat assistant a question](flowcharts/2-chatbot-request.png)
3. [Registering interest in a placement](flowcharts/3-expression-of-interest.png) (planned, not built yet)
4. [Downloading a course guide (members only)](flowcharts/4-gated-download.png)
5. [Searching the site](flowcharts/5-site-search.png)

Each chart has a .mmd file in flowcharts/ (the Mermaid source) next to its .png and .svg. To change a chart, edit the .mmd file and render it again, for example at mermaid.live, or with `npx @mermaid-js/mermaid-cli -i 1-register-login.mmd -o 1-register-login.png`.
