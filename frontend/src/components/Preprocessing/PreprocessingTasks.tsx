import { useMutatePreprocessingInstruction, usePreprocessingTasks } from "@/api/preprocessing";
import {
  AmcatField,
  AmcatFieldType,
  AmcatIndexId,
  PreprocessingInstruction,
  PreprocessingTask,
  UpdateAmcatField,
} from "@/interfaces";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { useEffect, useState } from "react";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "../ui/accordion";
import { Input } from "../ui/input";
import { Loading } from "../ui/loading";

import { useFields, useMutateFields } from "@/api/fields";
import { amcatPreprocessingInstruction, amcatPreprocessingInstructionArgumentValue } from "@/schemas";
import { AlertTriangle, ChevronDown } from "lucide-react";
import { z } from "zod";
import { Button } from "../ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "../ui/dropdown-menu";
import { Textarea } from "../ui/textarea";
import { useNavigate } from "@tanstack/react-router";
const useRouter = () => {
  const navigate = useNavigate();
  return { push: (to: string) => navigate({ to }) };
};

interface Props {
  indexId: AmcatIndexId;
  user: AmcatSessionUser;
}

export default function PreprocessingTasks({ indexId, user }: Props) {
  const { data: tasks, isLoading: isLoadingTasks } = usePreprocessingTasks(user);
  const { data: fields, isLoading: isLoadingFields } = useFields(user, indexId);

  if (isLoadingTasks || isLoadingFields) return <Loading />;
  if (!tasks || !fields) return null;

  return (
    <div className="max-w-lg">
      <h3 className="text-lg font-bold">Select preprocessor</h3>
      <Accordion type="single" collapsible>
        {tasks.map((task) => (
          <AccordionItem value={task.name} key={task.name}>
            <AccordionTrigger>{task.name}</AccordionTrigger>
            <AccordionContent>
              <TaskForm key={task.name} user={user} indexId={indexId} task={task} fields={fields} />
            </AccordionContent>
          </AccordionItem>
        ))}
      </Accordion>
    </div>
  );
}

type ArgumentValue = z.infer<typeof amcatPreprocessingInstructionArgumentValue>;

function TaskForm({
  user,
  indexId,
  task,
  fields,
}: {
  user: AmcatSessionUser;
  indexId: AmcatIndexId;
  task: PreprocessingTask;
  fields: AmcatField[];
}) {
  const { mutateAsync: mutateFields } = useMutateFields(user, indexId);
  const { mutateAsync: mutatePreprocessing } = useMutatePreprocessingInstruction(user, indexId);
  const [instruction, setInstruction] = useState(() => createInstructionTemplate(task));
  const router = useRouter();
  useEffect(() => setInstruction(createInstructionTemplate(task)), [task]);
  function instructionReady() {
    return (
      instruction.field &&
      instruction.endpoint &&
      instruction.arguments.every((arg) => (arg.value !== undefined && arg.value !== "") || arg.field) &&
      instruction.outputs.every((output) => output.field)
    );
  }

  async function UploadTaskInstruction(instruction: PreprocessingInstruction) {
    let newFields: UpdateAmcatField[] = [];
    if (!fields) return null;
    if (!instructionReady) return null;

    for (let output of task.outputs) {
      const name = instruction.outputs.find((out) => out.name === output.name)?.field;
      if (!fields.find((field) => field.name === name)) {
        newFields.push({
          name: name,
          // !!! TODO: type should be determined by the task definition.
          type: output.recommended_type,
          identifier: false,
        });
      }
    }
    const onReady = () => router.push(`/projects/${indexId}/settings`);
    if (newFields.length > 0) {
      mutateFields({ fields: newFields, action: "create" })
        .then(() => mutatePreprocessing(instruction))
        .then(onReady);
    } else mutatePreprocessing(instruction).then(onReady);
  }

  function keyHandler(key: keyof PreprocessingInstruction) {
    return (e: React.ChangeEvent<HTMLInputElement>) => setInstruction({ ...instruction, [key]: e.target.value });
  }

  function argValueHandler(name: string) {
    return (value: ArgumentValue) => {
      const args = [...instruction.arguments];
      const index = args.findIndex((arg) => arg.name === name);
      args[index].value = value;
      setInstruction({ ...instruction, arguments: args });
    };
  }
  function argFieldValueHandler(name: string) {
    return (value: string) => {
      const args = [...instruction.arguments];
      const index = args.findIndex((arg) => arg.name === name);
      args[index].field = value;
      setInstruction({ ...instruction, arguments: args });
    };
  }
  function outputFieldHandler(name: string) {
    return (field: string) => {
      const outputs = [...instruction.outputs];
      const index = outputs.findIndex((output) => output.name === name);
      outputs[index].field = field;
      setInstruction({ ...instruction, outputs });
    };
  }

  const labelStyle = "font-bold leading-8";
  const inputStyle = "bg-background/10";

  const nameTaken = fields.find((field) => field.name === instruction.field);

  return (
    <div className="prose flex  flex-col gap-1 rounded dark:prose-invert">
      <div className="rounded-t bg-primary p-6 text-primary-foreground">
        <h3 className="mt-0 text-primary-foreground">API Endpoint</h3>
        <Input className={inputStyle} id="endpoint" value={instruction.endpoint} onChange={keyHandler("endpoint")} />
      </div>
      <div className="bg-primary/30 p-6">
        <h3 className="mt-0">Input parameters</h3>
        <div className="flex flex-col gap-2 rounded">
          {task.parameters.map((par) => {
            const arg = instruction.arguments.find((arg) => arg.name === par.name);
            if (!arg) return null;
            return (
              <div key={par.name}>
                <label className={labelStyle} htmlFor={par.name}>
                  {par.name}
                </label>
                {par.use_field === "yes" ? (
                  <ArgumentFieldInput
                    fields={fields}
                    parameter={par}
                    value={arg.field || null}
                    onChange={argFieldValueHandler(arg.name)}
                  />
                ) : (
                  <ArgumentInput value={arg.value || ""} onChange={argValueHandler(arg.name)} />
                )}
              </div>
            );
          })}
        </div>
      </div>
      <div className="rounded-b bg-primary/50 p-6">
        <h3 className="mt-0">Output fields</h3>
        <div className="flex flex-col gap-2 rounded">
          {task.outputs.map((output) => {
            const value = instruction.outputs.find((out) => out.name === output.name)?.field ?? "";
            return (
              <div key={output.name}>
                <label className={labelStyle} htmlFor={output.name}>
                  {output.name}
                </label>
                <OutputField fields={fields} output={output} value={value} onChange={outputFieldHandler(output.name)} />
              </div>
            );
          })}
        </div>
      </div>
      <div className=" flex flex-col gap-1 rounded-t py-3">
        <div className="flex items-center gap-3">
          <h4 className="m-0 whitespace-nowrap ">Status field</h4>
          <Input
            className={`  focus-visible:ring-transparent ${
              nameTaken ? "bg-destructive text-destructive-foreground" : ""
            }`}
            id="field"
            value={instruction.field}
            onChange={keyHandler("field")}
          />
        </div>
        {nameTaken && (
          <div className="ml-auto flex items-center gap-3 px-3 py-1 text-sm text-destructive">
            <AlertTriangle /> Field name already exists
          </div>
        )}
      </div>
      <div className="flex justify-end gap-2 py-2">
        <Button
          disabled={!instructionReady()}
          variant="secondary"
          className="w-full"
          onClick={() => UploadTaskInstruction(instruction)}
        >
          {instructionReady() ? "Start preprocessor" : "Fill in all fields"}
        </Button>
      </div>
    </div>
  );
}

function OutputField({
  fields,
  output,
  value,
  onChange,
}: {
  fields: AmcatField[];
  output: PreprocessingTask["outputs"][0];
  value: string;
  onChange: (field: string) => void;
}) {
  const selectedField = fields.find((field) => field.name === value)?.name;
  const [input, setInput] = useState("");

  return (
    <div key={output.name} className="grid grid-cols-2 gap-2">
      <SelectField
        selectedField={selectedField ?? ""}
        setSelectedField={(value) => {
          setInput("");
          onChange(value);
        }}
        fields={fields}
        preprocessorType={output.type}
        disabled={!!value && !fields.find((field) => field.name === value)}
      />
      <Input
        className={input ? "bg-primary text-primary-foreground" : "bg-background/60"}
        value={input}
        placeholder={"create new"}
        onChange={(e) => {
          setInput(e.target.value);
          onChange(e.target.value);
        }}
      />
    </div>
  );
}

function ArgumentInput({ value, onChange }: { value: ArgumentValue; onChange: (value: ArgumentValue) => void }) {
  const [values, setValues] = useState(() => (Array.isArray(value) ? [...value, undefined] : [value]));
  useEffect(() => setValues(Array.isArray(value) ? [...value, undefined] : [value]), [value]);

  const isArray = Array.isArray(value);
  const type = isArray ? typeof value[0] : typeof value;

  function onChangeValue(newValue: string, index: number) {
    const newValues = [...values];
    newValues[index] = newValue;

    const v = newValues
      .map((v) => {
        if (v === "" && index > 0) return undefined;
        if (type === "number") return Number(v);
        if (type === "boolean") return Boolean(v);
        return v;
      })
      .filter((v) => v !== undefined);
    // had to resort to type coercion, because typescript is driving me mad
    onChange(isArray ? (v as ArgumentValue) : (v[0] ?? value));
  }

  return (
    <div className={` grid ${values.length > 1 ? "grid-cols-2" : "grid-cols-1"} gap-2 `}>
      {values.map((v, i) => {
        if (i > 0 && !values[i - 1] && !v) return null;
        const inputStyle = String(v ?? "")
          ? "bg-primary text-primary-foreground"
          : i === 0
            ? "bg-foreground/20 text-primary-foreground"
            : "resize-none bg-foreground/20 text-primary-foreground max-w-[3rem] rounded-full focus:rounded  focus:max-w-[30rem] hover:max-w-[30rem] transition-all";
        const showValue = String(v ?? "");
        if (type === "boolean")
          return (
            <Input
              key={i}
              value={showValue}
              type="checkbox"
              onChange={(e) => onChangeValue(e.target.checked ? "true" : "", i)}
            />
          );
        if (type === "number")
          return (
            <Input
              key={i}
              value={showValue}
              type="number"
              className={inputStyle}
              onChange={(e) => onChangeValue(e.target.value, i)}
            />
          );
        return (
          <Textarea
            key={i}
            rows={showValue.split("\n").length}
            className={`${inputStyle} min-h-[2.6rem]`}
            value={showValue}
            onChange={(e) => onChangeValue(e.target.value, i)}
          />
        );
      })}
    </div>
  );
}

function ArgumentFieldInput({
  fields,
  parameter,
  value,
  onChange,
}: {
  fields: AmcatField[];
  parameter: PreprocessingTask["parameters"][0];
  value: string | null;
  onChange: (value: string) => void;
}) {
  return (
    <div className="grid grid-cols-2 gap-2 ">
      <SelectField
        selectedField={value}
        setSelectedField={onChange}
        fields={fields}
        preprocessorType={parameter.type}
      />
    </div>
  );
}

function getAllowedFieldType(preprocessorType: string): AmcatFieldType[] {
  const isArray = /\[\]/.test(preprocessorType);
  if (/string/.test(preprocessorType)) {
    if (isArray) return ["tag"];
    return ["text", "keyword"];
  }
  if (/number/.test(preprocessorType)) {
    if (isArray) return ["vector"];
    return ["number", "integer"];
  }
  if (/boolean/.test(preprocessorType)) {
    if (isArray) return ["tag"];
    return ["boolean"];
  }
  if (/image/.test(preprocessorType)) return ["image"];
  if (/video/.test(preprocessorType)) return ["video"];
  if (/audio/.test(preprocessorType)) return ["audio"];
  return [];
}

function SelectField({
  selectedField,
  setSelectedField,
  fields,
  preprocessorType,
  disabled,
}: {
  selectedField: string | null;
  setSelectedField: (field: string) => void;
  fields: AmcatField[];
  preprocessorType: string;
  disabled?: boolean;
}) {
  const allowedTypes = getAllowedFieldType(preprocessorType);
  const allowedFields = fields.filter((field) => allowedTypes.includes(field.type));
  if (allowedFields.length === 0) return <div>No fields available</div>;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild disabled={disabled}>
        <Button
          variant={selectedField ? "default" : "outline"}
          className="flex h-10 items-center justify-between gap-2 text-left disabled:text-transparent"
        >
          {selectedField ? selectedField : "Select field"}
          <ChevronDown className="h-5 w-5" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent>
        {allowedFields.map((field) => (
          <DropdownMenuItem key={field.name} onClick={() => setSelectedField(field.name)}>
            {field.name}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function createInstructionTemplate(task: PreprocessingTask): PreprocessingInstruction {
  const args = task.parameters.map((param) => {
    const arg: any = { name: param.name, secret: !!param.secret };

    if (/string/.test(param.type)) {
      arg.value = param.default ?? "";
    } else if (/number/.test(param.type)) {
      arg.value = param.default ?? undefined;
    } else if (/boolean/.test(param.type)) {
      arg.value = param.default ?? false;
    } else if (/image|video|audio/.test(param.type)) {
      arg.value = param.default ?? "";
    }
    if (/\[\]/.test(param.type)) {
      arg.value = [arg.value];
    }

    if (param.use_field) arg.field = "";

    return arg;
  });

  const outputs = task.outputs.map((output) => {
    return { name: output.name, field: "" };
  });

  const template: PreprocessingInstruction = {
    field: task.name
      .replaceAll(" ", "_")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replaceAll(/[^a-zA-Z0-9_-]/g, "")
      .replace(/^[_-]+/, ""),
    task: task.name,
    endpoint: task.endpoint.placeholder ?? "",
    arguments: args,
    outputs,
  };

  return amcatPreprocessingInstruction.parse(template);
}
