import React, { useState } from "react";
import { Box, Text, useInput } from "ink";
import { colors, glyphs, spacing } from "../theme.js";
import { APPROVAL_OPTIONS } from "../planApproval.js";

interface Props {
  onApprove: () => void;
  onReject: () => void;
  onChange: (text: string) => void;
  disabled?: boolean;
}

type Mode = "picker" | "typing";

export function PlanApprovalPicker({ onApprove, onReject, onChange, disabled = false }: Props) {
  const [selected, setSelected] = useState(0);
  const [mode, setMode] = useState<Mode>("picker");
  const [value, setValue] = useState("");

  useInput((input, key) => {
    if (disabled) return;

    if (mode === "picker") {
      if (key.upArrow) {
        setSelected((i) => (i === 0 ? APPROVAL_OPTIONS.length - 1 : i - 1));
        return;
      }
      if (key.downArrow) {
        setSelected((i) => (i === APPROVAL_OPTIONS.length - 1 ? 0 : i + 1));
        return;
      }
      if (key.return) {
        const opt = APPROVAL_OPTIONS[selected];
        if (opt.key === "approve") onApprove();
        else if (opt.key === "reject") onReject();
        else setMode("typing");
        return;
      }
      // Number shortcuts (1/2/3)
      if (input === "1") setSelected(0);
      else if (input === "2") setSelected(1);
      else if (input === "3") setSelected(2);
      return;
    }

    // typing mode
    if (key.escape) {
      setMode("picker");
      setValue("");
      return;
    }
    if (key.return) {
      const trimmed = value.trim();
      if (trimmed) {
        setValue("");
        onChange(trimmed);
      }
      return;
    }
    if (key.backspace || key.delete) {
      setValue((v) => v.slice(0, -1));
      return;
    }
    if (!key.ctrl && !key.meta && input) {
      setValue((v) => v + input);
    }
  });

  if (mode === "typing") {
    return (
      <Box flexDirection="column">
        <Box
          marginX={spacing.sm}
          marginTop={spacing.xs}
          paddingX={spacing.xs}
          borderStyle="round"
          borderColor={colors.planMode}
        >
          <Text bold color={colors.planMode}>{glyphs.userPrefix} </Text>
          <Text>{value}</Text>
          <Text inverse>{" "}</Text>
        </Box>
        <Box marginX={spacing.sm}>
          <Text dimColor>Enter to send · Esc to go back</Text>
        </Box>
      </Box>
    );
  }

  return (
    <Box flexDirection="column">
      <Box
        marginX={spacing.sm}
        marginTop={spacing.xs}
        paddingX={spacing.sm}
        paddingY={0}
        borderStyle="round"
        borderColor={colors.planMode}
        flexDirection="column"
      >
        <Text bold color={colors.planMode}>Would you like to proceed?</Text>
        <Box height={1} />
        {APPROVAL_OPTIONS.map((opt, i) => {
          const active = i === selected;
          const num = `${i + 1}.`;
          if (active) {
            return (
              <Text key={opt.key} color={colors.planMode}>
                {`${glyphs.userPrefix} `}
                <Text inverse>{` ${num} ${opt.label} `}</Text>
              </Text>
            );
          }
          return (
            <Text key={opt.key} dimColor>
              {`  ${num} ${opt.label}`}
            </Text>
          );
        })}
      </Box>
      <Box marginX={spacing.sm}>
        <Text dimColor>↑/↓ to move · Enter to select · 1/2/3 shortcut</Text>
      </Box>
    </Box>
  );
}
