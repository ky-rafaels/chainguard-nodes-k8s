import json
import boto3
import os
import logging
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    # Get environment variables
    cluster_name = os.environ.get('CLUSTER_NAME')
    nodegroup_name = os.environ.get('NODEGROUP_NAME')
    region = os.environ.get('AWS_REGION', 'us-west-2')

    if not all([cluster_name, nodegroup_name, region]):
        logger.error("Missing required environment variables: CLUSTER_NAME, NODEGROUP_NAME, or AWS_REGION")
        return {
            'statusCode': 400,
            'body': json.dumps('Missing required environment variables')
        }

    try:
        # Initialize boto3 clients
        eks_client = boto3.client('eks', region_name=region)
        ssm_client = boto3.client('ssm', region_name=region)

        # Step 1: Get current node group details
        logger.info(f"Describing node group {nodegroup_name} in cluster {cluster_name}")
        response = eks_client.describe_nodegroup(
            clusterName=cluster_name,
            nodegroupName=nodegroup_name
        )
        nodegroup = response['nodegroup']
        current_k8s_version = nodegroup['version']
        current_release_version = nodegroup.get('releaseVersion', 'unknown')
        logger.info(f"Node group Kubernetes version: {current_k8s_version}, Current release version: {current_release_version}")

        # Step 2: Get the latest AMI release version from SSM
        ssm_parameter = f"/aws/service/eks/optimized-ami/{current_k8s_version}/amazon-linux-2/recommended/release_version"
        logger.info(f"Querying SSM parameter: {ssm_parameter}")
        try:
            ssm_response = ssm_client.get_parameter(Name=ssm_parameter)
            latest_release_version = ssm_response['Parameter']['Value']
            logger.info(f"Latest AMI release version: {latest_release_version}")
        except ssm_client.exceptions.ParameterNotFound:
            logger.error(f"SSM parameter {ssm_parameter} not found. Kubernetes version {current_k8s_version} may not be supported.")
            return {
                'statusCode': 400,
                'body': json.dumps(f"No AMI found for Kubernetes version {current_k8s_version}")
            }

        # Step 3: Check if update is needed
        if current_release_version == latest_release_version:
            logger.info("Node group is already using the latest AMI release version")
            return {
                'statusCode': 200,
                'body': json.dumps('Node group is up to date')
            }

        # Step 4: Initiate node group update
        logger.info(f"Updating node group to AMI release version {latest_release_version}")
        update_response = eks_client.update_nodegroup_version(
            clusterName=cluster_name,
            nodegroupName=nodegroup_name,
            releaseVersion=latest_release_version,
            force=False  # Respect Pod Disruption Budgets
        )

        update_id = update_response['update']['id']
        logger.info(f"Update initiated with ID: {update_id}")
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f"Node group update initiated to AMI release version {latest_release_version}",
                'updateId': update_id
            })
        }

    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        logger.error(f"ClientError: {error_code} - {error_message}")
        if error_code == 'ResourceNotFoundException':
            return {
                'statusCode': 404,
                'body': json.dumps(f"Cluster {cluster_name} or node group {nodegroup_name} not found")
            }
        elif error_code == 'InvalidParameterException':
            return {
                'statusCode': 400,
                'body': json.dumps(f"Invalid parameters: {error_message}")
            }
        else:
            return {
                'statusCode': 500,
                'body': json.dumps(f"Error updating node group: {error_message}")
            }
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f"Unexpected error: {str(e)}")
        }
</xai Artifact>

---

### **How It Works**
1. **Environment Variables**:
   - Reads `CLUSTER_NAME`, `NODEGROUP_NAME`, and `AWS_REGION` from Lambda environment variables.
   - Validates that all variables are set to prevent runtime errors.

2. **Node Group Details**:
   - Uses `eks:DescribeNodegroup` to get the node group’s current Kubernetes version (e.g., `1.26`) and release version (e.g., `1.26.12-20240307`).
   - Logs the current state for debugging.

3. **Latest AMI Retrieval**:
   - Queries the SSM Parameter Store path `/aws/service/eks/optimized-ami/<k8s_version>/amazon-linux-2/recommended/release_version` to get the latest AMI release version for the node group’s Kubernetes version.
   - Example: For Kubernetes 1.26, it might return `1.26.12-20240329`.

4. **Update Check**:
   - Compares the current release version with the latest. If they match, the function exits with a success message.
   - If different, it proceeds to update.

5. **Node Group Update**:
   - Calls `eks:UpdateNodegroupVersion` with the latest `releaseVersion`, keeping the Kubernetes version unchanged.
   - Sets `force=False` to respect Pod Disruption Budgets, ensuring graceful node draining (important for workloads like FastQC).
   - Returns the update ID for tracking.

6. **Error Handling**:
   - Handles common errors like `ResourceNotFoundException` (cluster/node group not found), `InvalidParameterException` (invalid parameters), and `ParameterNotFound` (unsupported Kubernetes version).
   - Logs errors to CloudWatch for debugging.

---

### **Deployment Instructions**

1. **Create the Lambda Function**:
   - In the AWS Lambda console, create a new function:
     - **Runtime**: Python 3.11
     - **Function name**: `UpdateEKSNodegroupAMI`
     - **Role**: Attach an IAM role with the permissions listed above.
   - Copy the `lambda_function.py` script into the code editor.

2. **Set Environment Variables**:
   - In the Lambda console, go to **Configuration > Environment variables** and add:
     - `CLUSTER_NAME`: `my-eks-cluster`
     - `NODEGROUP_NAME`: `my-eks-nodegroup`
     - `AWS_REGION`: `us-west-2`

3. **Configure Timeout and Memory**:
   - Set **Timeout** to 1 minute (the API calls are quick, typically <10 seconds).
   - Set **Memory** to 128 MB (sufficient for this script).

4. **Test the Function**:
   - Create a test event in the Lambda console:
     ```json
     {}
     ```
   - Run the test and check the CloudWatch logs for output:
     - Success: `Node group update initiated to AMI release version <version>`
     - No update needed: `Node group is up to date`
     - Error: Detailed error message

5. **Schedule Execution**:
   - Use Amazon EventBridge to trigger the Lambda function periodically (e.g., weekly):
     - Create a rule with a schedule expression (e.g., `rate(7 days)`).
     - Set the Lambda function as the target.

6. **Monitor Updates**:
   - Check the update status in the EKS console or via CLI:
     ```bash
     aws eks describe-update --cluster-name my-eks-cluster --nodegroup-name my-eks-nodegroup --update-id <update-id> --region us-west-2
     ```
   - View logs in CloudWatch under `/aws/lambda/UpdateEKSNodegroupAMI`.

---

### **Integration with Your Workflow**
- **EKS and FastQC**: This script ensures your EKS nodes run the latest AMI, which includes security patches and Kubernetes fixes, improving stability for containerized workloads like FastQC. The `force=False` setting minimizes disruptions to running Pods.
- **Docker and Multi-Stage Builds**: The script is independent of your FastQC container but ensures the underlying nodes are up to date, reducing the risk of compatibility issues with your distroless-based FastQC image.
- **Google Cloud Batch Comparison**: Unlike Google Batch (from your earlier questions), EKS requires manual or scripted updates for node AMIs. This Lambda function automates the process, similar to Batch’s managed resource provisioning.
- **Permissions**: The script avoids permission issues by using a properly configured IAM role, addressing concerns like those in your earlier FastQC Dockerfile questions (e.g., `mkdir /app not a directory`).

---

### **Limitations and Considerations**
1. **Managed Node Groups Only**:
   - The script works for EKS managed node groups, not self-managed node groups or custom AMIs. For custom AMIs, you’d need to update the launch template manually.[](https://docs.aws.amazon.com/cli/latest/reference/eks/update-nodegroup-version.html)

2. **Kubernetes Version**:
   - The script updates the AMI for the node group’s current Kubernetes version. To upgrade the Kubernetes version, modify the script to include the `--kubernetes-version` parameter in `update_nodegroup_version`.

3. **Pod Disruption Budgets**:
   - Setting `force=False` respects PDBs, but if PDBs prevent draining, the update may fail with a `PodEvictionFailure`. You can retry with `force=True` (edit the script), but this risks downtime.[](https://repost.aws/knowledge-center/eks-managed-node-group-update)

4. **SSM Parameter Availability**:
   - The script assumes the SSM parameter for the Kubernetes version exists. If the node group uses an unsupported version (e.g., deprecated), the script will fail gracefully.

5. **Custom AMIs**:
   - If your node group uses a custom AMI via a launch template, the script will fail unless you omit `releaseVersion` and specify a new launch template version. For custom AMIs, modify the script to update the launch template.[](https://docs.aws.amazon.com/eks/latest/userguide/launch-templates.html)

6. **Regional Availability**:
   - Ensure the SSM parameter and EKS cluster are in the same region as specified in `AWS_REGION`.

---

### **Testing and Validation**
- **Local Testing**:
   - Test the script locally using `boto3` by setting AWS credentials and environment variables:
     ```bash
     export AWS_ACCESS_KEY_ID=<key>
     export AWS_SECRET_ACCESS_KEY=<secret>
     export CLUSTER_NAME=my-eks-cluster
     export NODEGROUP_NAME=my-eks-nodegroup
     export AWS_REGION=us-west-2
     python3 lambda_function.py
     ```
   - Mock the Lambda event with an empty dictionary: `{}`.

- **Dry Run**:
   - Comment out the `update_nodegroup_version` call in the script and run it to log the current and latest release versions without initiating an update.

- **EKS Update Behavior**:
   - The update process creates a new launch template version, scales the Auto Scaling group, and drains nodes gracefully, ensuring minimal disruption. It may take 10+ minutes depending on the node count.[](https://www.eksworkshop.com/docs/fundamentals/managed-node-groups/basics/upgrades/)

---

### **Troubleshooting**
1. **ResourceNotFoundException**:
   - Verify the cluster and node group names exist:
     ```bash
     aws eks describe-nodegroup --cluster-name my-eks-cluster --nodegroup-name my-eks-nodegroup --region us-west-2
     ```

2. **ParameterNotFound**:
   - Check if the SSM parameter exists:
     ```bash
     aws ssm get-parameter --name /aws/service/eks/optimized-ami/1.26/amazon-linux-2/recommended/release_version --region us-west-2
     ```
   - Ensure the node group’s Kubernetes version is supported.

3. **PodEvictionFailure**:
   - If the update fails due to PDBs, check CloudWatch logs for details:
     ```bash
     aws logs filter-log-events --log-group-name /aws/lambda/UpdateEKSNodegroupAMI
     ```
   - Consider temporarily removing PDBs or using `force=True`.[](https://repost.aws/knowledge-center/eks-managed-node-group-update)

4. **InvalidParameterException**:
   - Ensure the node group wasn’t created with a custom AMI. If it was, update the launch template instead:
     ```bash
     aws eks update-nodegroup-version --cluster-name my-eks-cluster --nodegroup-name my-eks-nodegroup --launch-template '{"id":"lt-1234","version":"2"}' --region us-west-2
     ```

---

### **References**
- AWS EKS Documentation: [Update a Managed Node Group](https://docs.aws.amazon.com/eks/latest/userguide/update-managed-node-group.html)[](https://docs.aws.amazon.com/eks/latest/userguide/update-managed-node-group.html)
- AWS CLI Reference: [update-nodegroup-version](https://docs.aws.amazon.com/cli/latest/reference/eks/update-nodegroup-version.html)[](https://docs.aws.amazon.com/cli/latest/reference/eks/update-nodegroup-version.html)
- AWS EKS Workshop: [Upgrading AMIs](https://www.eksworkshop.com/intermediate/230_node_upgrades/)[](https://www.eksworkshop.com/docs/fundamentals/managed-node-groups/basics/upgrades/)
- AWS re:Post: [Troubleshoot Managed Node Group Updates](https://repost.aws/knowledge-center/eks-troubleshoot-managed-node-group-update)[](https://repost.aws/knowledge-center/eks-managed-node-group-update)

This Lambda script automates updating your EKS node group to the latest AMI release, ensuring your cluster stays secure and up to date for workloads like FastQC. If you need modifications (e.g., custom AMI support, Kubernetes version upgrades, or integration with CloudWatch Events), let me know!