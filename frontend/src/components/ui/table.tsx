import { cn } from "@/lib/utils";

export const Table = ({ children, className }: { children: React.ReactNode, className?: string }) => {
  return <table className={cn("", className)}>{children}</table>;
};

export const Td = ({ children, className }: { children: React.ReactNode, className?: string }) => {
  return <td className={cn("", className)}>{children}</td>;
};

export const Th = ({ children, className }: { children: React.ReactNode, className?: string }) => {
  return <th className={cn("", className)}>{children}</th>;
};

export const Tr = ({ children, className }: { children: React.ReactNode, className?: string }) => {
  return <tr className={cn("hover:bg-base-300", className)}>{children}</tr>;
};

export const Thead = ({ children, className }: { children: React.ReactNode, className?: string }) => {
  return <thead className={cn("", className)}>{children}</thead>;
};

export const Tbody = ({ children, className }: { children: React.ReactNode, className?: string }) => {
  return <tbody className={cn("", className)}>{children}</tbody>;
};