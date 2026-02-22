# NextJS client for Amcat4

## Run development version

First install stuff. Make sure you have a relatively recent version of node.

```
npm i
```

Make sure to create an .env.local file to set the AmCAT host, e.g.
by copying .env.local.example

```
cp dotenv.local.example .env.local
```

Run locally for development.

```
npm run dev
```


## UI

For components, we use [ShadCN](https://ui.shadcn.com/). 
To add a component, go to https://ui.shadcn.com/docs/components and follow  the instructions , e.g. `npx shadcn@latest add calendar`.
This copies the component source code into `components/ui` and can be imported (or modified) as desired

For styling, we use [Tailwind](https://tailwindcss.com/) for styling. 
If you feel a component should always have a specific styling, it should be edited in the component source as it is copy pasted anyway.


