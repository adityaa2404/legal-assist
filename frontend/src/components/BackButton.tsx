import React from 'react';
import { useNavigate } from 'react-router-dom';
import Icon from './ui/icon';

interface BackButtonProps {
    to?: string;
    label?: string;
}

const BackButton: React.FC<BackButtonProps> = ({ to, label = 'Back' }) => {
    const navigate = useNavigate();

    const handleClick = () => {
        if (to) {
            navigate(to);
        } else {
            navigate(-1);
        }
    };

    return (
        <button
            onClick={handleClick}
            className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors font-medium group"
        >
            <Icon name="arrow_back" size="sm" className="group-hover:-translate-x-0.5 transition-transform" />
            {label}
        </button>
    );
};

export default BackButton;
