"use client";

import { motion } from "framer-motion";

export function TypingIndicator() {
  return (
    <div className="flex space-x-1.5 p-2 items-center h-8">
      <motion.div
        className="w-2 h-2 bg-primary/60 rounded-full"
        animate={{ opacity: [0.3, 1, 0.3], scale: [0.8, 1, 0.8] }}
        transition={{ duration: 1.4, repeat: Infinity, ease: "easeInOut", delay: 0 }}
      />
      <motion.div
        className="w-2 h-2 bg-primary/60 rounded-full"
        animate={{ opacity: [0.3, 1, 0.3], scale: [0.8, 1, 0.8] }}
        transition={{ duration: 1.4, repeat: Infinity, ease: "easeInOut", delay: 0.2 }}
      />
      <motion.div
        className="w-2 h-2 bg-primary/60 rounded-full"
        animate={{ opacity: [0.3, 1, 0.3], scale: [0.8, 1, 0.8] }}
        transition={{ duration: 1.4, repeat: Infinity, ease: "easeInOut", delay: 0.4 }}
      />
    </div>
  );
}
