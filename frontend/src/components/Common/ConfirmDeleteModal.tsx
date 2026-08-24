import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Typography,
  Box,
  Slide,
  alpha,
  useTheme,
} from "@mui/material";
import { Warning } from "@mui/icons-material";
import { forwardRef } from "react";

const Transition = forwardRef(function Transition(props: any, ref: any) {
  return <Slide direction="up" ref={ref} {...props} />;
});

interface ConfirmDeleteModalProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  message: string;
  itemName?: string;
  isLoading?: boolean;
}

export default function ConfirmDeleteModal({
  open,
  onClose,
  onConfirm,
  title,
  message,
  itemName,
  isLoading = false,
}: ConfirmDeleteModalProps) {
  const theme = useTheme();

  return (
    <Dialog
      open={open}
      TransitionComponent={Transition}
      keepMounted
      onClose={!isLoading ? onClose : undefined}
      aria-describedby="alert-dialog-slide-description"
      PaperProps={{
        sx: {
          bgcolor: alpha('#1e293b', 0.95),
          backdropFilter: 'blur(20px)',
          border: '1px solid',
          borderColor: alpha('#475569', 0.3),
          borderRadius: 3,
          minWidth: 400,
          maxWidth: 500,
        },
      }}
    >
      <DialogTitle sx={{ pb: 2 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Box
            sx={{
              width: 48,
              height: 48,
              borderRadius: '50%',
              bgcolor: alpha(theme.palette.error.main, 0.1),
              border: `2px solid ${alpha(theme.palette.error.main, 0.3)}`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Warning sx={{ color: 'error.main', fontSize: '1.5rem' }} />
          </Box>
          <Box>
            <Typography variant="h6" fontWeight={600} color="text.primary">
              {title}
            </Typography>
            {itemName && (
              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                {itemName}
              </Typography>
            )}
          </Box>
        </Box>
      </DialogTitle>

      <DialogContent sx={{ pb: 3 }}>
        <Typography variant="body1" color="text.secondary" sx={{ lineHeight: 1.6 }}>
          {message}
        </Typography>
      </DialogContent>

      <DialogActions sx={{ px: 3, pb: 3, gap: 2 }}>
        <Button
          onClick={onClose}
          disabled={isLoading}
          variant="outlined"
          sx={{
            borderColor: alpha('#475569', 0.5),
            color: 'text.secondary',
            '&:hover': {
              borderColor: 'text.primary',
              bgcolor: alpha('#475569', 0.1),
            },
          }}
        >
          Annuler
        </Button>
        <Button
          onClick={onConfirm}
          disabled={isLoading}
          variant="contained"
          sx={{
            bgcolor: 'error.main',
            '&:hover': {
              bgcolor: 'error.dark',
            },
            '&:disabled': {
              bgcolor: alpha(theme.palette.error.main, 0.3),
            },
          }}
        >
          {isLoading ? 'Suppression...' : 'Supprimer'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}