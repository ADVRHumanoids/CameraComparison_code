# Camera comparison repository

This repository has two workflows for the depth-camera study:

| Folder | Purpose | Guide |
|---|---|---|
| [`data_collection/`](data_collection/README.md) | ROS 2 and Jetson environment for collecting camera recordings. | Setup, Docker, and acquisition |
| [`paper_reproduction/`](paper_reproduction/README.md) | Standalone processing and reproduction of the paper's numerical results, figures, and tables. | Python setup and `main.py` commands |

Use `data_collection/` when collecting new recordings with camera hardware.
Use `paper_reproduction/` to process the released dataset or reproduce the
paper without ROS, Jetson, or camera hardware.
