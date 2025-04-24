# EKS

## Dependencies

- eksctl (`brew install eksctl`)
- kubectl

## Create a nodegroup using AmazonLinux based AMI

Create a worker nodegroup 
```bash
eksctl create nodegroup \
  --cluster cgr-cluster-1 \
  --region us-east-2 \
  --name amazon-1-workers \
  --timeout 35m0s \
  --node-private-networking \
  --node-type t3.xlarge \
  --nodes 2 \
  --nodes-min 2 \
  --nodes-max 3 \
  --managed=true \
  --ami-family AmazonLinux2023
```
  <!-- --ssh-access \
  --cfn-disable-rollback \
  --ssh-public-key ~/.ssh/-shared.pub -->

## Generate cluster config and apply using `eksctl`

```bash
cat << EOF > cgr-cluster-1.yaml
apiVersion: eksctl.io/v1alpha5
kind: ClusterConfig
metadata:
  name: cgr-cluster-1
  region: us-east-2
vpc:
  clusterEndpoints:
    privateAccess: true
    publicAccess: false
  subnets:
    private:
      us-east-2a: { id: subnet-0f6aebfa6e98da2ef }
      us-east-2b: { id: subnet-06698e97e34d6e250 }
managedNodeGroups:
  - name: cgr-1-workers
    labels: { role: workers }
    instanceType: t3.xlarge
    desiredCapacity: 4
    privateNetworking: true
    ssh:
      allow: true
    #   publicKeyPath: "~/.ssh/-shared.pub"
EOF

eksctl create cluster -f cgr-cluster-1.yaml
```

## Create the new Chainguard nodegroup 

Create a new worker nodegroup using Chainguard AMI
```bash
eksctl create nodegroup \
  --cluster cgr-cluster-1 \
  --region us-east-2 \
  --name cgr-1-workers \
  --timeout 35m0s \
  --node-private-networking \
  --node-type t3.xlarge \
  --nodes 2 \
  --nodes-min 2 \
  --nodes-max 3 \
  --managed=true \
  --ami-family <cgr-ami> \
  --release-version <cgr-release-version> 
```

Ensure that the new nodegroup is added and healthy in cluster
```bash
kubectl get nodes 
```

We can now cordon, drain and remove our old nodegroup
```bash
kubectl cordon -l eks.amazonaws.com/nodegroup=amazon-1-workers

kubectl drain amazon-1-workers --ignore-daemonsets --delete-emptydir-data

eksctl delete nodegroup --cluster cgr-cluster-1 --name amazon-1-workers
```

## Next lets update our Chainguard nodes to a latest version

```bash
aws eks update-nodegroup-config \
    --cluster-name cgr-cluster-1 \
    --nodegroup-name cgr-1-workers \
    --release-version <new-ami-release-version>
```