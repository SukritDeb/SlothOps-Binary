import { Router } from "express";
import { getUserById } from "../services/userService";

const router = Router();

router.get("/:id", (req, res) => {
  const user = getUserById(req.params.id);
  if (!user) {
    return res.status(404).json({ error: "User not found" });
  }
  res.json(user);
});

router.get("/:id/profile", (req, res) => {
  const user = getUserById(req.params.id);
  
  if (!user) {
    return res.status(404).json({ error: "User not found" });
  }

  if (!user.profile) {
    return res.status(404).json({ error: "User profile not found or incomplete" });
  }


  // ✨ BUG 1 ✨
  // We assume user.profile always exists, but user "999" has a null profile.
  // This will throw: TypeError: Cannot read properties of null (reading 'displayName')
  const name = user.profile.displayName;

  res.json({
    message: `Welcome to the profile of ${name}`,
    avatar: user.profile.avatarUrl
  });
});

router.get("/:id/premium", (req, res) => {
  const userConfig: any = { features: null };
  // ✨ BUG: SaaS DEMO VULNERABILITY ✨
  // Throws TypeError: Cannot read properties of null (reading 'enabled')
  if (userConfig.features.enabled) {
    res.json({ premium: true });
  } else {
    res.json({ premium: false });
  }
});

export default router;
