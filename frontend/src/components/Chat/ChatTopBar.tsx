// © 2024–2026 TOURE Arnaud Patrick
// Licensed under the MIT License

import React, { useState } from "react";
import {
  Box,
  AppBar,
  Toolbar,
  Typography,
  IconButton,
  Avatar,
  Menu,
  MenuItem,
  Divider,
  alpha,
  useTheme,
} from "@mui/material";
import {
  AccountCircle,
  Settings,
  Logout,
} from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";

const ChatTopBar: React.FC = () => {
  const theme = useTheme();
  const navigate = useNavigate();
  const { logout, user } = useAuth();
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);

  const handleProfileMenuOpen = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget);
  };

  const handleProfileMenuClose = () => {
    setAnchorEl(null);
  };

  const handleLogout = () => {
    logout();
    navigate("/");
    handleProfileMenuClose();
  };

  const handleNavigate = (path: string) => {
    navigate(path);
    handleProfileMenuClose();
  };

  return (
    <AppBar
      position="static"
      elevation={0}
      sx={{
        bgcolor: alpha(theme.palette.background.paper, 0.8),
        backdropFilter: "blur(20px)",
        borderBottom: `1px solid ${theme.palette.divider}`,
        boxShadow: "none",
      }}
    >
      <Toolbar sx={{ justifyContent: "flex-end", pr: 2 }}>
        {/* Profile Menu Button */}
        <IconButton
          size="large"
          edge="end"
          onClick={handleProfileMenuOpen}
          color="inherit"
          sx={{ color: "text.primary" }}
          aria-label="profile menu"
        >
          <Avatar
            sx={{
              width: 32,
              height: 32,
              background: "linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)",
              fontSize: "0.875rem",
            }}
          >
            {user?.email?.[0]?.toUpperCase() || "U"}
          </Avatar>
        </IconButton>

        {/* Profile Menu */}
        <Menu
          anchorEl={anchorEl}
          anchorOrigin={{
            vertical: "bottom",
            horizontal: "right",
          }}
          keepMounted
          transformOrigin={{
            vertical: "top",
            horizontal: "right",
          }}
          open={Boolean(anchorEl)}
          onClose={handleProfileMenuClose}
          PaperProps={{
            sx: {
              bgcolor: alpha(theme.palette.background.paper, 0.95),
              backdropFilter: "blur(20px)",
              border: `1px solid ${theme.palette.divider}`,
            },
          }}
        >
          <MenuItem disabled sx={{ color: "text.secondary" }}>
            <Typography variant="body2">
              {user?.email || "Utilisateur"}
            </Typography>
          </MenuItem>
          <Divider />
          <MenuItem
            onClick={() => handleNavigate("/profile")}
            sx={{
              gap: 1.5,
              "& svg": { fontSize: "1.25rem" },
            }}
          >
            <AccountCircle fontSize="inherit" />
            <Typography variant="body2">Profil</Typography>
          </MenuItem>
          <MenuItem
            onClick={() => handleNavigate("/settings")}
            sx={{
              gap: 1.5,
              "& svg": { fontSize: "1.25rem" },
            }}
          >
            <Settings fontSize="inherit" />
            <Typography variant="body2">Paramètres</Typography>
          </MenuItem>
          <Divider />
          <MenuItem
            onClick={handleLogout}
            sx={{
              gap: 1.5,
              color: "error.main",
              "& svg": { fontSize: "1.25rem" },
            }}
          >
            <Logout fontSize="inherit" />
            <Typography variant="body2">Déconnexion</Typography>
          </MenuItem>
        </Menu>
      </Toolbar>
    </AppBar>
  );
};

export default ChatTopBar;
