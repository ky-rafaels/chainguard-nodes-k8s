#!/bin/bash
eksctl scale nodegroup --cluster cgr-cluster-1 --name cgr-1-workers --nodes 0 --nodes-max 3 --nodes-min 0
